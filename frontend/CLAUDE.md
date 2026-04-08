# Frontend — Medical MVP

## What This Is
Patient management frontend for Croatian private polyclinics. Part of a larger system with FastAPI backend, Tauri local agent, and CEZIH (national health IT) integration.

## Tech Stack
- **Next.js 16** (App Router, standalone output), React 19, TypeScript
- **Styling:** Tailwind CSS v4, shadcn/ui, tw-animate-css
- **State:** @tanstack/react-query v5 (server state), react-hook-form + zod (forms)
- **Icons:** lucide-react
- **API:** Cookie-based auth (httpOnly), custom fetch wrapper in `src/lib/api-client.ts`

## Project Structure

```
src/
├── app/
│   ├── (auth)/           # /prijava (login), /registracija (register)
│   └── (dashboard)/      # All authenticated routes
│       ├── dashboard/
│       ├── pacijenti/    # Patient CRUD + detail with tabs
│       ├── termini/      # Appointment scheduling + calendar
│       ├── postupci/     # Procedures catalog
│       ├── cezih-nalazi/ # CEZIH Nalazi + Biljeske tabs (clinical docs)
│       ├── cezih/        # CEZIH settings (config, agent, registri tabs)
│       ├── postavke/     # Settings (klinika, korisnici, sesije, tipovi-zapisa)
│       └── promjena-lozinke/
├── components/
│   ├── appointments/     # Calendar views, appointment CRUD (8 files)
│   ├── auth/             # Login/register forms, auth guard (3)
│   ├── biljeske/         # Internal clinical notes CRUD (3)
│   ├── cezih/            # CEZIH integration components (13)
│   ├── dashboard/        # Stats cards, today schedule, CEZIH widgets (3)
│   ├── documents/        # File upload/preview (3)
│   ├── layout/           # Header, sidebar, mobile nav, trial banner (5)
│   ├── medical-records/  # Record list/form/detail (3)
│   ├── patients/         # Patient table/search/form (3)
│   ├── prescriptions/    # Prescription CRUD (3)
│   ├── procedures/       # Procedure table/form + predracun (4)
│   ├── shared/           # Confirm dialog, spinner, pagination (4)
│   ├── ui/               # shadcn/ui primitives
│   └── users/            # User management (1)
├── lib/
│   ├── api-client.ts     # Fetch wrapper with auto-refresh, cookie auth
│   ├── auth.tsx          # AuthProvider context, useAuth hook
│   ├── constants.ts      # All Croatian labels, status maps, nav items, colors
│   ├── types.ts          # TypeScript interfaces for all API entities
│   ├── utils.ts          # cn() helper
│   └── hooks/            # 17 custom hooks (one per domain)
```

## Key Conventions
- **All UI text is in Croatian** (Hrvatski) — labels, statuses, navigation, error messages
- **Croatian label maps** live in `src/lib/constants.ts` — always use these, never hardcode Croatian strings in components
- **Navigation** is defined in `constants.ts` (`NAV_ITEMS` array) — add new routes there
- **API calls** go through `src/lib/api-client.ts` (`apiClient` function) — never use raw fetch
- **Hooks pattern:** One hook file per domain in `src/lib/hooks/use-{domain}.ts`, uses @tanstack/react-query
- **Forms:** react-hook-form + zod schema validation
- **Patient detail** page has tabs: Nalazi (CEZIH docs), Biljeske (internal notes), Termini, Postupci, Recepti, Dokumenti
- **CEZIH page** has tabs: Uputnice, Posjete, Slucajevi, Stranci, Aktivnost, Registri
- **Record types** are tenant-configurable via API — use `useRecordTypeMaps()` hook, not hardcoded constants
- **Nalazi** = CEZIH-eligible only (specijalisticki_nalaz, nalaz). Other clinical note types go to **Biljeske**

## CEZIH Components (13 files in components/cezih/)
These handle all CEZIH national health system integration UI:
- Visit management (create/close/reopen/storno)
- Case management (ICD-10 search, create, status transitions, data update)
- Document operations (send/replace/cancel/search/retrieve)
- Insurance check, foreigner registration, patient selector
- Registry tools (OID lookup, ValueSet expand, organization/practitioner search)
- Activity log, mock badge, eKarton view

## Development
- Run via Docker Compose: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`
- Frontend at http://localhost:3000, backend API at http://localhost:8000/api
- After code changes: `docker compose restart frontend` (hot reload misses some changes)

@AGENTS.md
