---
date: 2026-04-27
topic: signing | extsigner | certilia-mobile | vendor-coordination
status: resolved
---

# CEZIH extsigner `ERROR_CODE_0018` — `Presign failed: Unauthorized` from CEZIH→Certilia hop (4-day outage, 24.04 → 27.04)

> **Resolved 2026-04-28** — root cause was different from this finding's attribution. The missing credential was on **our** side (we weren't sending an `Authorization: Bearer <token>`), not on CEZIH's downstream Certilia presign side. CEZIH had unilaterally tightened extsigner auth on/around 2026-04-23. Wiring `_get_signing_token()` into `sign_bundle_via_extsigner` resolved it. See **`2026-04-28-extsigner-bearer-token-required.md`** for the full resolution. The vendor coordination saga below is preserved as historical record (and as a lesson — Certilia and AKD were correct in saying they hadn't changed anything).

## Discovery

Starting 2026-04-24 ~07:32 UTC (09:32 CEST), every Certilia-mobile signing
attempt is rejected at **step 1** (the `extsigner/api/sign` POST itself, before
any phone push) with:

```json
{"error":{
  "errorCode":{"system":"rdss-service","code":"ERROR_CODE_0018"},
  "errorDescription":"Presign failed: {\n  \"message\":\"Unauthorized\",\n  \"request_id\":\"<id>\"\n}"
}}
```

Different code from the 2026-04-21 outage (`ERROR_CODE_0020`, AKD e-potpis
proxy 404). This one is `ERROR_CODE_0018` and the `errorDescription` shows
the failing hop is CEZIH's **internal call to the Certilia cloud signer**
(presign), authorising itself with whatever credential CEZIH has on file for
our `sourceSystem` / OIB. That credential is now rejected.

Reproduced consistently across 4 days, ~half a dozen attempts at different
times, identical error body, different inner Certilia `request_id` each time.
Last verified-good Certilia-mobile sign was 2026-04-22 afternoon (per `2026-04-22-certilia-mobile-afternoon-reverify.md`). The 2026-04-23 sweep was smart-card only; the planned Certilia-mobile companion sweep that day was an open action item that never got executed, so 22.04 afternoon is the documented green-water-mark on this signing path.

## Smoking-gun evidence — smart card path works on the same bundle

This is the part that pinpoints the failure to the CEZIH↔Certilia hop and
nothing else:

- **2026-04-27 13:26:14 UTC** — `extsigner/api/sign` (Certilia path) → HTTP 500 `ERROR_CODE_0018` "Presign failed: Unauthorized" (Certilia request_id `5cb46a6fe711c05989f33e5a90ab1f00`)
- **2026-04-27 13:28:34 UTC** — same, retry → HTTP 500 (Certilia request_id `486cf516decba130a1ce19518d28e052`)
- **2026-04-27 13:33:40 UTC** — same user (OIB 15881939647), same backend, same patient, **same FHIR Bundle**, switched signing method to AKD smart card → `POST /api/cezih/visits → 200 OK` (11.6 s, ES384 JWS, kid `b2fff6b771609c91…`)

7-minute window, single variable changed (signing method). Therefore:

- FHIR bundle is valid (CEZIH accepted it, no warnings)
- OAuth2 token for `certws2.cezih.hr:8443` is valid
- mTLS / agent session is healthy
- `certws2.cezih.hr:8443` endpoint for visits is up
- OIB 15881939647 is correctly registered on CEZIH side
- The pad is **isključivo** between CEZIH's `extsigner` gateway and the
  Certilia cloud signer it calls downstream

## Vendor coordination loop (and what each said)

The error gives no hint which side owns the broken credential. Pinging all
three vendors in parallel revealed:

| Date (CEST) | Vendor | Channel | Verdict |
|---|---|---|---|
| 2026-04-24 09:51 | HZZO "Provjera Spremnosti" (Natalija) | existing thread, CEZIH testna okolina report | "Šaljem ENT-u na provjeru." (forwarded to integrator, no further reply yet) |
| 2026-04-24 11:00 | AKD `helpdesk-tpd@akd.hr` | new ticket, full logs | replied 2026-04-27 07:52 — "Molimo Vas da se za navedenu poteškoću obratite na e-mail adresu: esign@certilia.com" — out of AKD scope |
| 2026-04-27 17:32 | Certilia `esign@certilia.com` | forwarded from AKD with full logs | replied 17:48 (Luka Mandić) — asked which API key we use for presign calls |
| 2026-04-27 ~17:55 | (us → Luka) | replied: we send no API key, only `oib` + `sourceSystem` + `requestId` + `documents`, mTLS at TLS layer | — |
| 2026-04-27 ~18:00 | Certilia (Luka Mandić) | replied: "Sa naše strane nije bilo nikakvih promjena na sustavu. Kako CEZIH-ov sustav radi i šta koristi za pozive na to vam ne znam odgovor, za te informacije morate kontaktirati njihov support/helpdesk." |

Net result: AKD says it's not theirs (they don't run the e-signature
gateway anymore for this flow), Certilia explicitly denies any change on
the cloud signer side, HZZO/ENT is the only remaining owner of the
extsigner→presign credential configuration.

Email drafts saved to repo root (so they are versioned with the project,
not lost in inboxes):

- `bug-report-email-akd.txt` — original technical report (originally to
  AKD, redirected to Certilia; sent 2026-04-27 with both 24.04 + 27.04
  reproductions and smart-card success)
- `bug-report-email-2.txt` — reply to Luka Mandić clarifying the request
  shape and asking three pointed questions (what extra identifier do we
  need, is it CEZIH's API key that rotated, was there a 22.04→24.04 spec
  change)
- `bug-report-email-cezih.txt` — follow-up to the existing Provjera
  Spremnosti / ENT thread with the 4-day persistence update and
  smart-card-200-OK contrast (the deciding piece of evidence for ENT)

## Why the request shape matters

Our extsigner POST contains literally:

```json
{
  "oib": "15881939647",
  "sourceSystem": "HM-DIGITAL-MEDICAL",
  "requestId": "<uuid>",
  "documents": [{
    "documentType": "FHIR_MESSAGE",
    "mimeType": "JSON",
    "base64Document": "<b64>",
    "messageId": "<uuid>"
  }]
}
```

with `Content-Type: application/json`, no `Authorization` header, no API
key field. Auth to the gateway is mTLS via the agent's smart-card client
cert at the TLS layer. We confirmed this is the working configuration
(adding a Bearer token causes 401 — see `cezih_signing.py:535`,
"Auth: mTLS via agent session — NO Bearer token (adding one causes 401)").

That means: no credential we send can have rotated or expired, because we
don't carry any. The credential that became "Unauthorized" lives **inside
CEZIH's extsigner**, used by it when it calls Certilia presign on our
behalf.

## Impact

- Blocks every Certilia-mobile-signed TC: TC11 register, TC12/13/14 visits,
  TC16/17 case lifecycle, TC18/19/20 ITI-65 send/replace/storno
- Smart-card path is unaffected and verified green on the same day for
  every TC family - see `2026-04-23-smartcard-sweep-green.md`
- Per `feedback_signing_independence` rule, both methods must work
  independently for certification, so this is a **P0 blocker for the
  Certilia-mobile half of the cert exam**, even though smart card is fine
- **Exam is 2026-04-28** (tomorrow as of this writing). Last-minute escalation
  added to the email sent 2026-04-27 evening: "Ukoliko se nešto promjenilo a
  mi ne znamo, molim Vas da nam javite, jer imamo dogovoren ispit za sutra."
  If recovery does not land before exam start, fall back to smart-card-only
  with the written attestation per Action Items.
- Same outage class as `2026-04-21-extsigner-akd-epotpis-down.md` -
  CEZIH-side gateway plumbing fails, our payload never gets evaluated

## Lessons learned

1. **`ERROR_CODE_0018` "Presign failed: Unauthorized" is NOT us.** When the
   extsigner gateway returns an `errorDescription` that quotes a
   downstream HTTP message verbatim (`"message":"Unauthorized"` with a
   downstream `request_id`), that downstream side owns the error. Nothing
   to debug in our payload, no Bearer header to add, no `sourceSystem` to
   change — the configuration that needs rotating is on CEZIH (or one
   layer beyond, but reachable only through CEZIH).

2. **Smart-card path is the gold-standard isolator.** When the Certilia
   path fails, switching the same user's `cezih_signing_method` to
   `smartcard` and replaying the same operation tells you immediately
   whether the bundle/OAuth/endpoint are healthy. This is faster than any
   tcpdump or back-and-forth with vendors.

3. **Vendor escalation order:** for an `extsigner/...:Presign failed`
   outage, go HZZO/Provjera Spremnosti → ENT first; AKD will redirect to
   Certilia, Certilia will deny and bounce back to CEZIH. Save a round-trip
   by pinging the existing Provjera Spremnosti thread on day 1 and only
   widening to AKD/Certilia in parallel as belt-and-braces.

4. **Save the emails in-tree.** Vendor email threads are evidence. We've
   started saving outbound drafts as `bug-report-email-*.txt` in repo root;
   they get committed with the rest of the project so future sessions
   (and any cert auditor who asks "what did you do when X broke") can read
   the actual coordination history, not a summary.

5. **Test-env credentials drift on short timescales too.** Last verified-good
   Certilia-mobile sign was 2026-04-22 afternoon, only ~36-48 hours before
   the first 24.04 morning failure. CEZIH test environment routinely has
   presign credentials, mTLS bundles, or internal proxies expire/rotate
   without notice, and the rotation window can be a single weekend. Any
   future "did this silently break?" investigation should first check date
   of last green run vs date of first failure, then look at vendor-side
   rotation schedules. **Lesson for our own discipline:** when a planned
   companion sweep is in the action items (e.g. 2026-04-23 smart-card sweep
   listed "Certilia-mobile companion sweep today" as TODO), do it the same
   day - the one we skipped on 23.04 would have narrowed the failure window
   from ~48h to ~24h.

## Action Items

- [x] **Sent** `bug-report-email-cezih.txt` 2026-04-27 evening as a reply
      on the existing Provjera Spremnosti / Natalija thread, AKD +
      Certilia esign on CC, plus an exam-tomorrow nudge ("imamo dogovoren
      ispit za sutra").
- [x] ~~**Wait for ENT** to acknowledge / fix the extsigner→Certilia
      credential.~~ **N/A 2026-04-28** — root cause was on our side
      (missing Bearer header), not ENT's. Resolved by EXP-3, no ENT
      action needed. See `2026-04-28-extsigner-bearer-token-required.md`.
- [x] **On recovery**: Certilia-mobile end-to-end verified 2026-04-28
      08:58 (visit-create HTTP 200, full Certilia push round-trip ~26s).
      Single-operation reverify; full sweep deferred until post-cert.
- [x] ~~**If ENT asks for additional logs**~~ — N/A, fixed in-house.
- [x] ~~**If recovery slips past exam date**~~ — N/A, fixed
      2026-04-28 morning ahead of any rescheduled exam slot.
