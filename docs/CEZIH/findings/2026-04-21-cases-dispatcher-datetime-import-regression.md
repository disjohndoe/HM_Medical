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
- [x] Commit fix + deploy
- [ ] Retry TC17c Zatvori (Resolve / 2.5) — verify status transitions to Zatvoren + Završetak filled on top J06.9 row
- [ ] Exercise TC17b-recur (2.2 Ponavljajući) on a Zatvoren case to cover the other fix site

## Note — action/event-code mapping discrepancy (observational, not this bug)

The signed bundle for `action="resolve"` carried `MessageHeader.eventCoding.code="2.4"`, but per CLAUDE.md the event codes are 2.3 Remission / 2.4 Relapse / 2.5 Resolve. The `findings/case-lifecycle-profile-matrix.md` entry notes the old code had these swapped. Worth double-checking the current builder still sends the correct code for Resolve, once 2.5 is re-tested. Tracking under case-lifecycle-profile-matrix.md rather than here.
