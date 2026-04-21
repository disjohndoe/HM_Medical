---
date: 2026-04-21
topic: errors
status: resolved
---

# cases.py dispatcher — missing `datetime`/`UTC` import crashes 2.5/2.2

## Discovery

TC17c (Zatvori / 2.5 Resolve) via Certilia mobile failed with HTTP 500:

```
{"detail":"Dogodila se neočekivana greška."}
```

Backend log:

```
ERROR [app.error_handler] Unhandled exception on PUT /api/cezih/cases/{case_id}/status
NameError: name 'datetime' is not defined
```

## Evidence

`backend/app/services/cezih/dispatchers/cases.py` calls `datetime.now(UTC)` at:

- L375 (`create_recurring` / 2.2) — onset_date fallback
- L402 (post-create mirror) — onset_date fallback
- L417 (resolve / 2.5) — abatement_date

But the module imported only `logging` and `uuid.UUID`; `datetime`/`UTC` were not imported. Every call site that actually fires the `datetime.now(UTC)` branch crashes with `NameError`. All of Certilia signing + bundle build + CEZIH POST succeeds; the crash happens in the *local-mirror update* after the CEZIH call. The CEZIH state therefore ends up `resolved` server-side, but our UI rolls back the optimistic "Zatvoren" to the previous status.

Regression from commit `14377a3` (`refactor(cezih): split dispatcher/service/message_builder into domain packages`). Split moved the code out of the old monolithic dispatcher.py into `dispatchers/cases.py` without bringing the `from datetime import UTC, datetime` line along. `visits.py`, `documents.py`, and `patient.py` all got the import; `cases.py` did not.

Signing path trace from production logs (`2026-04-21 04:46–04:47`):
1. Extsigner POST/poll loop succeeds (`signatureStatus: NOTIFICATION_SENT`, signed bundle returned).
2. Bundle with `"code":"2.4"` [sic — see "Action mapping" below], `clinicalStatus.code=resolved`, `abatementDateTime=2026-04-21T06:46:45+02:00` is built and signed.
3. Pre-flight GET `/Condition?_count=0` returns 400 `Missing mandatory parameter "patient" in the query` (non-fatal WARNING — proceeds).
4. Bundle POSTed to CEZIH (body logged, no explicit response line in excerpt — POST likely succeeded).
5. Control returns to `dispatch_update_case` → mirror-update branch at L417 → `NameError`.

## Impact

- TC17c (Resolve / 2.5 via mobile) fails with generic 500 even though CEZIH-side state is updated.
- TC17a "Ponavljajući" / 2.2 (`create_recurring`) also broken — same missing import, same `datetime.now(UTC)` at L375.
- Reopen (2.7) path at L419 uses `clear_abatement=True` only, no datetime call, so 2.7 was not affected.
- Remission (2.3), Relapse (2.4) do not hit `action == "resolve"` so the L417 branch returns `None` for `abatement_date` and the bug is dormant for them — they worked in TC17a/b above.

## Action Items

- [x] Add `from datetime import UTC, datetime` to `backend/app/services/cezih/dispatchers/cases.py`
- [x] Commit fix + deploy (commit `98184c6`)
- [x] Retry TC17c Zatvori (Resolve) — **VERIFIED 2026-04-21 06:58** on Aktivan+Potvrđen J11 case (20.04.2026 15:24 → Zatvoren, Završetak 21.04.2026). Toast "Zatvori — uspješno". PUT 200. No more 500/NameError.
- [x] Ponovno otvori (Reopen, 2.9) — **VERIFIED 2026-04-21 07:0x** on the same J11 case (Zatvoren → Aktivan). PUT 200. Confirms local-mirror update path (L419 clear_abatement branch) is intact.
- [ ] Exercise TC17b-recur (2.2 Ponavljajući) via Novi slučaj dialog to cover the other datetime fix site (L375)

## Note — event-code mapping is CORRECT (not a bug)

The signed bundle for `action="resolve"` carries `MessageHeader.eventCoding.code="2.4"`. Global CLAUDE.md lists 2.4=Relapse/2.5=Resolve, but that's outdated — per live testing in `findings/case-lifecycle-profile-matrix.md` and the code comments at `builders/condition.py:233-236`, the CORRECT (verified) mapping is **2.4=Resolve, 2.5=Relapse** (Simplifier cezih.hr.condition-management/0.2.1). This was pinned down in commit `b314a4e` (2026-04-16).

## Note — state-machine rejection on Relaps → Resolve (separate from this bug)

First retry attempt hit the **top row (Relaps state)**. CEZIH returned 400 with `ERR_HEALTH_ISSUE_2004: "Not allowed to perform requested transition with current roles."` This is CEZIH's state machine rejecting a direct Relaps → Resolve transition — the code is not about user roles (see profile matrix, line 66-68). The fix is to pick a case in `aktivan+potvrđen` state to exercise 2.4 Resolve; the second retry on J11 (aktivan+potvrđen) succeeded.

**Observed FE state-machine gap** (`frontend/src/components/cezih/case-management.tsx:248-249`): `relapse → [remission, resolve]`, but CEZIH disallows direct Relaps → Resolve. The profile matrix documents Zatvori as valid only on `aktivan`. FE should drop `resolve` from the `relapse` gate (or require an intermediate Remisija). Tracked as a separate UX cleanup — not a cert blocker since 2.4 is not in the 22 TCs.
