# pvpri Production Switch — app.hmdigital.hr → CEZIH production

One-time flip of the production backend from the CEZIH **test** environment
(`certws2`/`certsso2`) to CEZIH **production** (`ws2`/`sso2`), once the first
real client is ready. Full hostname/env mapping lives in
`docs/runbooks/cezih-env-switch.md` — this file is the operational procedure.

## Prerequisites (all must be true before flipping)

1. **Production OAuth2 client credentials** for our info system:
   `CEZIH_CLIENT_ID` + `CEZIH_CLIENT_SECRET` valid at
   `https://sso2.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token`
   (client_credentials grant). Test-realm credentials do NOT work here.
   Request via helpdesk@hzzo.hr if not delivered with the cooperation agreement.
   Also confirm the prod OAuth2 URL for the extsigner (Certilia) signing flow —
   test uses `certpubsso.cezih.hr`; prod is expected to be the same `sso2` realm.
2. First real client onboarded in the app (tenant, users, their real AKD cards).
3. Client machine(s): Cisco AnyConnect profile → `pvpri.cezih.hr`
   (161.53.103.153, tcp/443 — verified live 2026-09-07). Auth = AKD card
   certificate; no separate VPN credentials exist.
4. First client's CEZIH identity configured on their Tenant: šifra ustanove +
   generated info-system OID (Postavke > Organizacija → "Generiraj OID")
   and each doctor's OIB (auto-filled from the AKD card, or Postavke >
   Korisnici). Institution identity is per-tenant/per-user in the DB — not env.

## The flip

```bash
ssh root@178.104.169.150
cd /opt/medical-mvp
cp .env .env.backup-test-$(date +%Y%m%d%H%M)   # rollback point
```

Edit `.env` (values per the mapping runbook):

```
CEZIH_OAUTH2_URL=https://sso2.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token
CEZIH_FHIR_BASE_URL=https://ws2.cezih.hr:8443
CEZIH_FHIR_AUX_URL=https://ws2.cezih.hr:9443
CEZIH_SIGNING_URL=https://ws2.cezih.hr:8443
CEZIH_SIGNING_OAUTH2_URL=<prod signing realm — confirm, see prerequisite 1>
CEZIH_CLIENT_ID=<production client id>
CEZIH_CLIENT_SECRET=<production client secret>
```

(Institution identity — šifra ustanove, info-system OID, signer OIB — lives
on Tenant/User rows in the DB, not in `.env`.)

```bash
docker compose up -d backend          # recreate to load new .env
docker compose logs backend --tail 50 # verify clean startup
```

## Verification (with the client, on prod)

1. `https://app.hmdigital.hr/api/health` → ok
2. Agent paired from the web app (released agents default to
   `wss://app.hmdigital.hr/`; allowlist `lib.rs:217`)
3. Smoke: TC6 OID generation against the **prod** registry (creates the
   info-system/document OIDs)
4. One smartcard sign + one Certilia sign with the client's card
5. One real document (e-Nalaz) submitted and confirmed on eKarton

## Rollback

```bash
cp .env.backup-test-YYYYMMDDHHMM .env && docker compose up -d backend
```

Local/TEST testing is unaffected — the local stack keeps its own `.env`
pointed at the test environment (see `cezih-env-switch.md`).

## After the flip

- Certification-era test tenants/patients still live in the prod DB — decide
  on cleanup before more real client data lands.
- Multi-client identity is per-tenant/per-user in the DB (no env identity):
  `Tenant.sifra_ustanove` + `Tenant.oid` (Postavke > Organizacija) and
  `User.card_certificate_oib` for the Certilia signer OIB (Postavke >
  Korisnici, auto-filled from the AKD card). Onboard each client's values
  there — a second client needs no code or env changes.
- Agent-side VPN status check hosts (`HM_CEZIH_VPN_HOSTS`) default to the
  test hosts; point prod clients' installs at `ws2.cezih.hr:8443,...` or make
  it backend-driven.
