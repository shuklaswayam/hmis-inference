# Frontend — HMIS Intelligence Platform

React 19 + TypeScript + Vite single-page app for Gujarat's HMIS situational-awareness dashboard. Sits in front of the FastAPI service in `../backend/` and the ChromaDB-RAG pipeline in `../backend/rag/`.

## Stack

- **React 19 + TypeScript** with `vite` for dev server and bundling
- **Tailwind CSS** with design tokens wired through `src/design/tokens.ts` and CSS variables in `src/index.css`
- **Radix UI primitives** (avatar, dialog, dropdown, scroll-area, separator, tabs, tooltip, ...) wrapped under `src/components/ui/`
- **Framer Motion** for the staggered command palette, spring expand on alert rows, and sidebar collapse transitions
- **Leaflet + react-leaflet** for the Gujarat district choropleth (`GujaratMap.tsx`, geometry in `public/gujarat_districts.json`)
- **Recharts** for analytics charts
- **TanStack Query** for server-state, axios for transport
- **Jotai** for cross-page UI state (e.g. inspector/chat panels)
- **cmdk** for the ⌘K command palette
- **lucide-react** icons

See `REDESIGN_SPEC.md` in this folder for the design tokens, ASCII mockups, and accessibility matrix that the components are built against.

## Develop

```bash
npm install
cp .env.example .env
npm run dev      # http://localhost:5173
```

The dev server talks to whatever `VITE_API_BASE_URL` is set to (default `http://localhost:8000`). Make sure the backend is running first — `GET /api/v1/alerts/` and `/api/v1/districts/risk-summary` are required for the Overview page to render.

## Build

```bash
npm run build                # outputs to dist/
npm run preview              # serve the built bundle locally
```

If the backend has `API_KEY` set, pass it at build time so the SPA can authenticate:

```bash
VITE_API_KEY=your-shared-secret npm run build
```

`src/api/client.js` reads this at build time and forwards it as `X-API-Key` on every request.

## Layout

```
src/
├── layouts/AppShell.tsx                # Sidebar + TopBar + outlet (per REDESIGN_SPEC §2)
├── pages/                              # one file per top-level route
│   ├── OverviewPage.tsx                # AI ribbon + KPI grid + map + alert feed
│   ├── AlertsPage.tsx
│   ├── InvestigationsPage.tsx
│   ├── AnalyticsPage.tsx
│   ├── FacilitiesPage.tsx
│   ├── AIPage.tsx                      # AI Workspace
│   ├── ReportsPage.tsx
│   ├── SettingsPage.tsx
│   └── placeholders.tsx
├── components/
│   ├── layout/                         # CommandPalette, PageHeader
│   ├── ui/                             # Radix-wrapped primitives
│   ├── AlertFeed.tsx, AlertDetail.tsx, AlertCard.tsx
│   ├── AIChat.tsx                      # slide-in chat panel
│   ├── ExecutiveKPI.tsx
│   ├── GujaratMap.tsx
│   └── DistrictFilter.tsx
├── api/client.js                       # axios instance, VITE_API_KEY wiring
├── design/tokens.ts                    # typed token map (spacing, radius, color)
├── lib/{utils,nav}.ts
├── types/{alerts,react-leaflet}.d.ts
└── router.tsx
```

Keyboard shortcuts wired in `AppShell.tsx`:

- `⌘K` / `Ctrl-K` — open command palette
- `⌘I` / `Ctrl-I` — toggle right inspector drawer
- All other nav shortcuts (`G O`, `G A`, `G I`, ...) are listed in `lib/nav.ts` and surface in the command palette

## Conventions

- All new components are `.tsx`. The codebase used to mix `.jsx` and `.tsx`; the rewrite is complete and new components should be TypeScript.
- Styling uses `cn()` from `lib/utils.ts` (clsx + tailwind-merge). Avoid inline `style={{...}}` except for dynamic 3rd-party props.
- Keep imports through the `@/` alias (configured in `tsconfig.json` + `vite.config.js`).
- Tests are not yet wired. When adding them, prefer Vitest + Testing Library; the alerts feed and command palette are the highest-leverage targets.
