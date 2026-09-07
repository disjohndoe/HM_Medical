# CEZIH Environment Switch — Test ↔ Production

How to run the app against the CEZIH **test** environment (local dev) versus the
**production** environment (app.hmdigital.hr for real clients). The switch is
**env-vars only** — no code changes.

## Hostnames

| Purpose | Test | Production | Reachable from |
|---|---|---|---|
| Clinical FHIR (8443) | `certws2.cezih.hr:8443` | `ws2.cezih.hr:8443` | agent (VPN) only |
| Aux: OID, terminology, mCSD (9443) | `certws2.cezih.hr:9443` | `ws2.cezih.hr:9443` | agent (VPN) only |
| OAuth2 token | `certsso2.cezih.hr` | `sso2.cezih.hr` | agent (VPN) only |
| Remote signing (extsigner) | `certws2.cezih.hr:8443` | `ws2.cezih.hr:8443` (or `pubws.cezih.hr:443`, public) | agent / public |
| Signing OAuth2 | `certpubsso.cezih.hr` | see sso2 above | agent (VPN) only |
| VPN gateway (AnyConnect) | `pvsek.cezih.hr` | `pvpri.cezih.hr` (161.53.103.153) | public |

Production = test hostname without the `cert` prefix. Verified 2026-09-07:
the backend reaches CEZIH **only through the local agent relay** — the Hetzner
server itself cannot resolve/connect to any CEZIH host except `pubws.cezih.hr:443`.
VPN is Cisco AnyConnect authenticated by the AKD card certificate.

## Environment variables (backend `.env`)

```
CEZIH_OAUTH2_URL=https://{certsso2|sso2}.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token
CEZIH_FHIR_BASE_URL=https://{certws2|ws2}.cezih.hr:8443
CEZIH_FHIR_AUX_URL=https://{certws2|ws2}.cezih.hr:9443
CEZIH_SIGNING_URL=https://{certws2|ws2}.cezih.hr:8443
CEZIH_SIGNING_OAUTH2_URL=https://{certpubsso|sso2}.cezih.hr/auth/realms/CEZIH/protocol/openid-connect/token
CEZIH_ORG_CODE=<test 999001464 | real client šifra ustanove>
CEZIH_CLIENT_ID / CEZIH_CLIENT_SECRET=<test realm | PRODUCTION sso2 realm creds>
```

Agent side (optional): `HM_CEZIH_VPN_HOSTS` — hosts used for the VPN status
check (defaults to the test hosts; point to `ws2.cezih.hr:8443,...` for prod clients).

## Local development = CEZIH TEST environment

1. `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
   (backend http://localhost:8000, frontend http://localhost:3000, db :5433;
   `.env` holds the test CEZIH credentials + random local secrets)
2. Local agent: `cd local-agent && pnpm tauri dev`, set the backend URL in the
   agent UI to **http://localhost:8000** (CSP already allows `ws://localhost:8000`)
3. Cisco AnyConnect → `pvsek.cezih.hr` + test AKD card (card #558299)
4. Expected on startup without VPN: `HZZO initial sync failed` log line (not fatal)

## Production flip (app.hmdigital.hr → CEZIH prod) — PREREQUISITES

1. **Production OAuth2 client credentials** for the `sso2` realm — request via
   helpdesk@hzzo.hr if not delivered with the signed cooperation agreement.
2. First real client onboarded: šifra ustanove, HZJZ šifre, MBOs, their AKD
   cards/Certilia, AnyConnect profile → `pvpri.cezih.hr` on their machines.
3. Prod info-system OID generated via TC6 against the prod registry.

## Production flip procedure

```bash
ssh root@178.104.169.150
cd /opt/medical-mvp
cp .env .env.backup-test-$(date +%Y%m%d)   # rollback point
# edit .env: swap cert* hosts for prod hosts per table above,
# set prod CEZIH_CLIENT_ID/SECRET, set real client CEZIH_ORG_CODE
docker compose up -d backend                 # recreate to load new .env
docker compose logs backend --tail 50        # verify startup
```

Rollback: restore the backup `.env` and `docker compose up -d backend` again.

## Known gaps (2026-09-07)

- `CEZIH_ORG_CODE` / `CEZIH_OID` / signer OIB are **global** env vars — fine for
  one client, must become per-tenant (DB) config before the second institution.
- Prod DB still contains certification-era test tenants/patients — decide on
  cleanup before real client data lands.
