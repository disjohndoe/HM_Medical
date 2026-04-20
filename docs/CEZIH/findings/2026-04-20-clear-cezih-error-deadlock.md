---
date: 2026-04-20
topic: errors
status: resolved
---

# `clear_cezih_error` self-deadlock on retry-after-error path (TC19)

## Discovery

TC19 (replace clinical document) hung indefinitely on a retry after the first attempt hit a transient CEZIH 400 (`ERR_DOCTRANSVAL_1000` — CEZIH test env's internal FHIR server `localhost:8080` flake, see `2026-04-20-cezih-test-env-fhir-server-down.md`).

Second attempt: CEZIH returned **200 OK** (replace succeeded server-side, new OID `746554` superseding `746552`), but our backend never returned to the client. No completion log, no DB commit, no response. Frontend dialog stuck on "Spremanje...".

## Evidence

Backend log ends abruptly right after the CEZIH 200:

```
17:05:22,205 CEZIH response via agent: POST .../iti-65-service -> 200 (1501.4ms)
17:05:22,205 CEZIH response body length: 4773 chars
[…nothing more for this request…]
```

DB state after the hang (confirmed via `psql`):

```
cezih_reference_id     = 1401554                                (unchanged, old value)
cezih_document_oid     = 2.16.840.1.113883.2.7.50.2.1.746552    (unchanged, old value)
cezih_last_error_code  = ERR_DOCTRANSVAL_1000                   (set by 1st attempt at 17:05:01)
updated_at             = 17:05:01                               (time of the 1st attempt's 400)
```

CEZIH state (from the request body sent at 17:05:11): new `DocumentReference` with `masterIdentifier = urn:oid:…746554` and `relatesTo.target = urn:oid:…746552` with code `replaces`. CEZIH accepted it (200).

## Root cause

`backend/app/services/cezih/error_persistence.py:clear_cezih_error` opened a **new** `AsyncSession` via `async_session()` to run its `UPDATE medical_records SET cezih_last_error_* = NULL WHERE id = X AND cezih_last_error_code IS NOT NULL`.

The dispatcher's request-scoped session had already, earlier in the same function, done:

```python
setattr(record, "cezih_reference_id", new_ref)
setattr(record, "cezih_document_oid", new_oid)
# …other edits…
await db.flush()               # writes pending UPDATE, acquires row lock, no commit yet
await clear_cezih_error(...)   # ← opens fresh session, same-row UPDATE
                               #   blocks on the row lock held by the first session
                               #   first session is awaiting this call → deadlock
```

Why this hadn't surfaced before: the `clear_cezih_error` UPDATE has `WHERE code_col IS NOT NULL`, so on happy-path retries (no prior error) it matches zero rows and doesn't contend. TC19's prior 400 set `cezih_last_error_code`, so the retry's `clear_cezih_error` matched → deadlock.

The docstring on `clear_cezih_error` already said "Intended to run inside the main dispatcher transaction — so it shares the commit". The implementation contradicted that.

## Fix

`clear_cezih_error` now takes `*, session: AsyncSession | None = None`. When the caller passes its `db`, the UPDATE runs inside the caller's transaction (no self-deadlock, and the clear is atomic with the state change — matching the docstring's original intent). When `session=None`, falls back to a fresh session + commit (preserved for any non-dispatcher caller).

All 9 call sites updated to pass `session=db` (visits.py ×2, cases.py ×2, documents.py ×5).

## Impact

Any dispatcher flow where a row had a prior `cezih_last_error_code` and a subsequent retry succeeded was vulnerable. Triggered in practice on flaky CEZIH test env where transient 400/5xx on first attempt is common.

**User-facing symptom:** submit dialog stuck on "Spremanje..." (action button disabled) until user closes it; local DB state diverges from CEZIH (CEZIH accepted the operation, local record still shows pre-operation values).

## Diagnostic hint for future

When a PUT/POST CEZIH endpoint hangs and backend log ends at "CEZIH response body length: N chars", check whether the target row had `cezih_last_error_code` populated. If so, suspect this class of self-deadlock. Backend restart is the only way to unstick the hung worker — the uncommitted transaction rolls back, leaving the local row at its pre-call state while CEZIH retains whatever it committed.
