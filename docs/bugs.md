# Bug Ledger

Chronological log of non-trivial bugs discovered in production and how they were fixed. Append new entries at the top.

Format per entry:
- **ID** — short slug (date + topic)
- **Discovered / Fixed** — dates
- **Severity** — blocker | major | minor
- **Where** — file(s) + component
- **What** — symptom
- **Why** — root cause
- **Fix** — what shipped
- **Verified** — how we confirmed

---

## 2026-04-20 — tempId optimistic-row PATCH race (Posjete + Slučajevi)

- **ID:** `2026-04-20-tempid-optimistic-row`
- **Discovered:** 2026-04-20 during CEZIH E2E on prod (smart card, TC12→TC13 back-to-back)
- **Fixed:** 2026-04-20
- **Severity:** blocker for certification — user cannot do create→edit without reloading, which the on-site exam requires
- **Where:**
  - `frontend/src/components/cezih/visit-management.tsx`
  - `frontend/src/components/cezih/case-management.tsx`
  - (mutation layer untouched: `frontend/src/lib/hooks/use-cezih.ts`)

### What (symptom)

1. Doctor clicks "Nova posjeta" → fills form → "Kreiraj posjetu".
2. Optimistic row appears in the table with `visit_id = "temp-1776666613732"`.
3. Before the CEZIH signing round-trip returns (5–10 s), doctor clicks the pencil on that new row.
4. Edit dialog opens with title `Izmjena posjetetemp-1776666613732`, user submits.
5. `PATCH /api/cezih/visits/temp-1776666613732?patient_id=...` → **502**.
6. Only way out: page reload.

Same pattern for Slučajevi (`temp-` and `pending-` prefixes).

### Why (root cause)

React Query's optimistic-create pattern (`useCreateVisit`, `useCreateCase` in `use-cezih.ts`) inserts a row with `visit_id = "temp-<ts>"`. On `onSuccess`, the tempId is swapped for the real CEZIH id in the query cache. Until the swap completes, the component lets the user open the edit dialog on that row, which captures `v.visit_id = "temp-..."` into `editVisitId` state. The subsequent PATCH hits a URL with the tempId — the backend has no such visit and returns 502.

### Fix (shipped)

Three layers of defense in `visit-management.tsx` and `case-management.tsx`:

1. **Hide/disable actions on optimistic rows.** `isOptimistic(row)` checks `temp-`/`pending-` prefix. `canEdit()` and `getAvailableActions()` return false/[] while optimistic. The always-rendered pencil in case-management is disabled via `disabled={isOptimistic(c)}`.
2. **Visual indicator.** Optimistic rows show `<Loader2 /> Sprema se...` in the Akcije column so the doctor understands the row is mid-save.
3. **Handler guards.** `startEdit`, `handleEdit`/`handleEditSave`, `handleAction` all bail with a Croatian toast ("Pričekajte dovršetak kreiranja...") if the id is still optimistic. Belt-and-braces against fast-click races before React re-renders the disabled attribute.

No backend changes. Behavior on real-id rows is unchanged.

### Verified

- Typecheck clean locally (`pnpm exec tsc --noEmit`).
- Prod E2E: TBD — run TC12 create → immediately TC13 edit without reload; confirm pencil is disabled until row reconciles, then click succeeds and PATCH hits the real cuid.

### Related

- `docs/CEZIH/findings/tempid-remount-race-fix.md` (certification-facing finding)
- Memory: `feedback_optimistic_row_remount_race.md` (pattern rule)
- Earlier partial fix: commit `1aa776f` closed the create dialog BEFORE the mutation to prevent a separate Base UI Select wedge caused by the same row remount. This bug (stale tempId on edit) is adjacent but different — the dialog timing fix didn't cover the edit-button race.
