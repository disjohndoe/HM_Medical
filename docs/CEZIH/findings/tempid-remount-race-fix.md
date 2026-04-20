---
date: 2026-04-20
topic: frontend-ux
status: resolved
---

# Optimistic tempId PATCH race — Posjete + Slučajevi

## Discovery

During CEZIH E2E on prod (smart card, GORAN PACPRIVATNICI19), the first "Izmijeni podatke posjete (1.2)" click immediately after "Nova posjeta" (1.1) always 502'd. Same class of bug exists for Slučajevi (TC16 → TC17 back-to-back).

The on-site certification exam at HZZO runs the 22 TCs as a sequence. TC12 → TC13 (create → update visit) is expected to work without a page reload. This blocked that path.

## Evidence

Observed on `app.hmdigital.hr`:

- Dialog title after clicking pencil on fresh row: `Izmjena posjetetemp-1776666613732`
- Network: `PATCH https://app.hmdigital.hr/api/cezih/visits/temp-1776666613732?patient_id=... → 502`
- After page reload, same row re-rendered with real id `cmo6tg2tp01x2hb855luwtmgt`; PATCH succeeded.

Code path:

- `frontend/src/lib/hooks/use-cezih.ts:427` — `useCreateVisit.onMutate` inserts `{ visit_id: "temp-<ts>" }`.
- `frontend/src/lib/hooks/use-cezih.ts:453` — `onSuccess` swaps tempId for real `resp.visit_id`.
- Gap between those two = 5–10 s (CEZIH signing round-trip). During that window the table row exists with tempId.

Same pattern for cases: `use-cezih.ts:618` (`temp-`) and `use-cezih.ts:710` (`pending-` for `create_recurring`).

## Impact

**Certification blocker.** TC12→TC13 and TC16→TC17 sequences fail on first attempt. Doctors who followed the natural flow would see a 502, blame the software, and need a reload to recover. Unacceptable during a supervised on-site exam.

Independent of signing method (card or Certilia).

## Action Items

Shipped 2026-04-20 in `visit-management.tsx` + `case-management.tsx`:

1. `isOptimistic(row)` helper — treats `temp-*` (visits + cases) and `pending-*` (recurring cases) as optimistic.
2. `canEdit` and `getAvailableActions` return false/`[]` on optimistic rows → pencil and Akcija dropdown hidden.
3. Case pencil (always rendered) gets `disabled={isOptimistic(c)}` with "Čeka potvrdu CEZIH-a..." tooltip.
4. Inline `<Loader2 /> Sprema se...` indicator in the Akcije column so the doctor knows the row is mid-save.
5. `startEdit`, `handleEdit`/`handleEditSave`, `handleAction` all guard against optimistic ids with a Croatian toast — belt-and-braces for fast-click races.

Verify before next certification attempt: TC12 → TC13 back-to-back on prod, no reload, PATCH targets real cuid.

See also: `docs/bugs.md` entry `2026-04-20-tempid-optimistic-row`.
