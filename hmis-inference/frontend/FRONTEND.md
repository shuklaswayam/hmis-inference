# Frontend — HMIS Intelligence Platform

React 19 + TypeScript single-page app that consumes the FastAPI backend. This doc complements [REDESIGN_SPEC.md](./REDESIGN_SPEC.md) (design tokens + a11y matrix) and the system-level [ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Stack

- React 19, TypeScript 5.7, Vite 8, Tailwind 3.4
- Routing: `react-router-dom@7` (BrowserRouter, declared once in `src/router.tsx`)
- State: `@tanstack/react-query@5` for server cache, `jotai` for shared UI state, local `useState` for component-local
- UI primitives: Radix UI wrapped in `src/components/ui/*` (button, dialog, dropdown-menu, command palette, etc.)
- Charts: `recharts` for time-series + KPI tiles
- Map: `leaflet` + `react-leaflet` for the Gujarat district overlay
- Animation: `framer-motion` in `AppShell` and `CommandPalette`
- HTTP: `axios` with a 120 s timeout (set in the shared client) for slow LLM-synthesis routes

## Routing

`src/router.tsx` declares the SPA. All paths are nested inside `<AppShell />`:

| Path | Page | Purpose |
|---|---|---|
| `/` | `OverviewPage` | Executive dashboard — KPIs, district map, top alerts |
| `/alerts` | `AlertsPage` | Filterable, severity-sorted alert feed; opens detail modal |
| `/investigations` | `InvestigationsPage` | Open incident view + linked alerts |
| `/facilities` | `FacilitiesPage` | Facility directory with risk + capacity columns |
| `/analytics` | `AnalyticsPage` | Trend explorer (per-facility metric over time) |
| `/ai` | `AIPage` | AI Workspace — chat with the policy-grounded Q&A |
| `/reports` | `ReportsPage` | District / facility static reports |
| `/settings` | `SettingsPage` | API key + connection status |
| `/gantt` | redirect → `/reports` | Legacy route alias |
| `*` | `NotFoundPage` | Fallback |

## Shell — `src/layouts/AppShell.tsx`

Three-column layout:

1. **Left sidebar** — collapsed-by-default (64 px), expands on hover or click (240 px). Header logo (`Activity` icon, "Artem / Gujarat HMIS"). Five inline nav items (`Overview`, `Alerts`, `Investigations`, `AI Intelligence`, `Settings`) with badge counters. Footer ribbon shows the model accuracy stat. Bottom toggle button collapses the sidebar.
2. **Top bar (48 px)** — breadcrumb (auto-built from pathname), command-palette trigger (`⌘K`), theme toggle, AI chat toggle, inspector toggle.
3. **Main canvas** — 1200 px max-width content area (`<Outlet />`).

Two optional overlay surfaces:

- **Right Inspector** — `⌘I`; shows keyboard shortcuts and platform status. 320 px.
- **AI Chat slide-in** — opens from the top-bar button or via `commandOpen` from the palette; 300 px.

The shell also owns theme state (`localStorage` key `hmis:theme`) — defaults to dark.

## Component map

```
src/
├── App.tsx                  ← React Query provider, QueryClient config
├── main.tsx                 ← Vite entry; mounts <App /> in #root
├── router.tsx               ← BrowserRouter + Routes
├── design/tokens.ts         ← import-only design tokens (colors, spacing, scale, ...)
├── layouts/
│   └── AppShell.tsx
├── lib/
│   ├── utils.ts             ← cn() — clsx + tailwind-merge wrapper
│   └── nav.ts               ← PRIMARY_NAV / INTELLIGENCE_NAV / SECONDARY_NAV / ALL_NAV
├── pages/
│   ├── OverviewPage.tsx
│   ├── AlertsPage.tsx
│   ├── InvestigationsPage.tsx
│   ├── FacilitiesPage.tsx
│   ├── AnalyticsPage.tsx
│   ├── AIPage.tsx
│   ├── ReportsPage.tsx
│   ├── SettingsPage.tsx
│   └── placeholders.tsx     ← NotFoundPage
├── components/
│   ├── AlertFeed.tsx        ← real-time WebSocket feed (useWebSocketHook)
│   ├── AlertCard.tsx
│   ├── AlertDetail.tsx
│   ├── AIChat.tsx
│   ├── DistrictFilter.tsx
│   ├── ExecutiveKPI.tsx
│   ├── GujaratMap.tsx       ← react-leaflet choropleth
│   ├── layout/
│   │   ├── CommandPalette.tsx
│   │   └── PageHeader.tsx
│   └── ui/                  ← Radix-wrapped primitives (button, dialog, command, dropdown, ...; + skeleton, badge, separator, scroll-area, gantt, card, avatar, input, tooltip, context-menu)
└── types/
    ├── alerts.ts            ← Alert / Insight / Forecast type defs
    └── react-leaflet.d.ts   ← ambient types
```

## Design tokens — `src/design/tokens.ts`

The design system is tokenised and consumed through Tailwind config (`tailwind.config.js`) and direct imports. See `REDESIGN_SPEC.md` for the visual mock, the a11y matrix, and the typographic scale. Tokens are kept import-only so consumers (`cn()`, page-level components) can `import { colors } from '@/design/tokens'` without a runtime cost.

## Server-state cache

TanStack Query's `QueryClient` is configured at `src/App.tsx`. Default stale time is 60 s; the live alert feed configures `staleTime: 0` + `refetchInterval: 30 s` plus a WebSocket listener that invalidates on frame receipt. `axios` is shared through `lib/api.ts` (axios instance with the 120 s timeout and the `X-API-Key` header if `VITE_API_KEY` is set at build time).

## WebSocket

`AlertFeed` opens `ws://<host>/ws/alerts` and maps incoming frames onto the query cache. Connection drops are silently retried with exponential backoff; when the socket is offline, the component falls back to the 30 s refetch.

## Environment variables

Set at build time via `.env` (use `.env.example` as the template):

| Var | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend root, e.g. `http://localhost:8000` |
| `VITE_API_KEY` | If set, sent as `X-API-Key` on every request |

## Local dev

```bash
cd hmis-inference/frontend
npm install
npm run dev    # http://localhost:5173
```

Production build: `npm run build` → `dist/` (nginx serves it from `/` with SPA fallback to `index.html`).

## Testing

`vitest` + `@testing-library/react` + jsdom. Smoke tests live next to source:

- `src/lib/__tests__/utils.test.ts` — `cn()` reorder + conflict resolution
- `src/lib/__tests__/nav.test.ts` — `ALL_NAV` shape, unique paths, shortcut coverage
- `src/components/ui/__tests__/button.test.tsx` — render + class merge

Run: `npm test` (CI mode) or `npm run test:watch` (interactive).
