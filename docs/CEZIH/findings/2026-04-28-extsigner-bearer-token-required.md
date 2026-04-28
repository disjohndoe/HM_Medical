---
date: 2026-04-28
topic: signing | extsigner | auth
status: resolved
---

# Extsigner now requires `Authorization: Bearer <token>` (CEZIH unilateral change ~2026-04-23)

## Discovery

Starting on/around 2026-04-23, every Certilia-mobile signing attempt failed at step 1 (`POST .../extsigner/api/sign`) with `HTTP 401 "Greška 401. Zahtjev nije autenticiran"` or `HTTP 500 ERROR_CODE_0018 "Presign failed: Unauthorized"`. Result in production: every `POST /api/cezih/visits → 502`.

The predecessor finding (`2026-04-27-extsigner-certilia-presign-unauthorized.md`) attributed the outage to a CEZIH-side credential rotation between CEZIH's gateway and Certilia. **That attribution was wrong.** The credential that needed to change was on **our** side: CEZIH had silently tightened the auth requirements on `extsigner/api/sign` to require an OAuth2 Bearer token in addition to the agent's mTLS session.

## Root cause

CEZIH unilaterally tightened auth on `https://certws2.cezih.hr:8443/services-router/gateway/extsigner/api/sign` (and `getSignedDocuments`) on/around 2026-04-23.

**Pre-2026-04-23 contract** (verified-good through 2026-04-22 afternoon):
- mTLS session via agent's smart-card cert at TLS layer
- No `Authorization` header (adding one returned 401 — this was a real, observed behavior at that time)

**Post-2026-04-23 contract** (current as of 2026-04-28):
- mTLS session via agent (unchanged) — required
- **Plus** `Authorization: Bearer <token>` from `https://certpubsso.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token` (OAuth2 `client_credentials`, our `CEZIH_CLIENT_ID` + `CEZIH_CLIENT_SECRET`) — newly required

`sign_bundle_via_extsigner` was sending only mTLS, no Bearer. The `_get_signing_token` helper and the `CEZIH_SIGNING_OAUTH2_URL` env var had been wired into the codebase for ages but were never called from the actual signing flow — the OAuth2 plumbing existed but was disconnected.

The pre-existing inline comment at `cezih_signing.py:535` (`"Auth: mTLS via agent session — NO Bearer token (adding one causes 401)"`) was historically correct and went stale on 2026-04-23. Acted on like a hard rule, it kept us from trying the obvious fix for several days.

## Evidence

Three experiments on 2026-04-28, fully logged at `~/.claude/plans/extsigner-experiment-log.md`:

**EXP-1 (~08:43) — config-only fix, disproven:**
- Set `CEZIH_FHIR_PUB_BASE_URL=https://certpubws.cezih.hr:8443` so extsigner traffic would target the documented "public" host.
- Result: agent could not reach `certpubws.cezih.hr:8443` (`curl: [28] Timeout was reached`). The "public, no VPN" assumption in the inline comment doesn't hold for our network — only `certws2.cezih.hr:8443` is reachable from the agent. Setting `CEZIH_FHIR_PUB_BASE_URL` also redirected unrelated working endpoints (QEDM `list_visits`, etc.) to the unreachable host.
- Rolled back. Total time: 6 min.

**EXP-2 (~08:51) — OAuth2 reachability probe:**
- Added a temporary admin-only `GET /api/_diag/signing-token-probe` route that called `_get_signing_token(httpx.AsyncClient())` and reported the result.
- Probe response: `{"oauth_url": "https://certpubsso.cezih.hr/auth/...", "client_id_set": true, "agent_connected": true, "should_use_agent": true, "token_acquired": true, "token_preview": "eyJhbGciOiJSUzI1NiIs...94zQWOCr4Uzg (len=1526)"}`.
- 163 ms round-trip via the agent to `certpubsso.cezih.hr:443`. Token TTL 300s. Plumbing fully functional — just disconnected.
- Probe torn down immediately after read.

**EXP-3 (~08:57) — wire Bearer into `sign_bundle_via_extsigner`:**
- Patched `cezih_signing.py` (+12/-2 lines) to call `_get_signing_token` once before step 1 POST and reuse the token across both step 1 and step 2 GET poll.
- Live trace from logs:
  ```
  08:57:37  signing auth: token acquired (expires_in=300s)              [2.1s]
  08:57:37  POST .../extsigner/api/sign  →  201 (1995ms)  ← was 401/500 before
  08:57:39  step 1 OK: transactionCode=eyJh...
  08:57:39  poll 1/60  →  400 ERROR_CODE_0022 phase=HASH_SENT  (waiting on phone)
  08:57:44  poll 2/60  →  400 ERROR_CODE_0022 phase=HASH_SENT
  08:57:49  poll 3/60  →  400 ERROR_CODE_0022 phase=HASH_SENT
  08:57:54  poll 4/60  →  400 ERROR_CODE_0022 phase=HASH_SENT
  08:58:00  poll 5/60  →  200  signatureStatus=NOTIFICATION_SENT  ← phone tap
  08:58:01  POST /api/cezih/visits  →  200 (26693ms)
  ```
- Same token used for step 1 and step 2 (token TTL 300s ≈ polling timeout 300s; user phone tap typically arrives in 30–60s, so re-fetch wasn't necessary).

## Fix

Commit `960cf3e fix(cezih): wire Bearer token into extsigner sign + poll calls` on `main`. Diff:

```python
# Step 1: Submit document for signing
# EXP-3 (2026-04-28): CEZIH started rejecting unauthenticated extsigner
# requests around 2026-04-23 (401 / 500 ERROR_CODE_0018 Presign Unauthorized).
# Acquire Bearer via existing OAuth2 client_credentials flow against
# certpubsso (probed working). Reused for step-2 polling below.
async with httpx.AsyncClient() as _bearer_client:
    bearer_token = await _get_signing_token(_bearer_client)

# ... unchanged log line ...

sign_result = await _request_via_agent(
    method="POST",
    url=sign_url,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",   # NEW
    },
    ...
)

# (step 2 polling GET — same Authorization header added to its headers dict)
```

## Verification

End-to-end on `app.hmdigital.hr` 2026-04-28 08:58:01 — `POST /api/cezih/visits → 200 OK` (26.7s round-trip including Certilia phone approval). Agent v0.13.0, smart card #558299, Certilia mobile push approved by user. CEZIH accepted the visit; downstream side effects (visit row in DB, audit entry) verified normal.

## Lessons

1. **`ERROR_CODE_0018 "Presign failed: Unauthorized"` is *not necessarily* a downstream-only error.** The `errorDescription` quoting `{"message":"Unauthorized"}` from a downstream `request_id` led us to conclude the broken credential lived inside CEZIH's extsigner→Certilia hop. It can equally mean "we (CEZIH) couldn't authenticate ourselves to Certilia *because YOU didn't give us the credentials we now require to forward*". When you see this error, also test sending a Bearer token before assuming the failure is purely vendor-side. The 04-27 finding's vendor coordination loop (4 days, 3 vendors, 2 dead-ends) could have been short-circuited by a probe.

2. **Inline code comments asserting "X causes Y" need a verified-against date.** The comment `"NO Bearer token (adding one causes 401)"` was correct on 2026-04-13 (per TC11 finding evidence) and silently flipped on 2026-04-23. With no anchor date, future engineers (us) treated it as a permanent rule. New convention: any comment of the form `"do/don't X because vendor behavior Y"` must read like `"# verified 2026-04-13: do/don't X because Y"`. If it's >30 days old and the vendor relationship is involved, treat with skepticism.

3. **Probe-via-temp-endpoint is high-leverage.** The `_diag` route was 60 lines, deployed in <2 min, ran once, torn down in <2 min, and saved a deploy cycle that would have failed on OAuth2 reachability if we'd jumped straight to EXP-3. Keep this pattern in the toolkit for any "is the plumbing actually connected end-to-end?" question.

4. **Both signing methods don't share the same auth model.** Smart card path doesn't go through extsigner — it signs locally and the FHIR call uses the agent's existing mTLS session at port 8443 against, e.g., `$process-message`. The Bearer requirement is specifically on the extsigner endpoints. So when CEZIH made this change, smart card stayed green (per `2026-04-23-smartcard-sweep-green.md`) while Certilia mobile broke. The independence rule held; only the Certilia path needed fixing.

## See also

- `2026-04-27-extsigner-certilia-presign-unauthorized.md` — predecessor finding documenting the 4-day outage and vendor coordination saga (now marked resolved).
- `TC11-PMIR-auth-blocker.md` — the original 2026-04-13 finding where `"NO Bearer token / mTLS only"` guidance was first documented (now annotated with a 2026-04-28 update).
- `~/.claude/plans/extsigner-experiment-log.md` — full experiment log with EXP-1/2/3 outcomes and rollback commands.
