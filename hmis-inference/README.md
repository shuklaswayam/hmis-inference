# HMIS Intelligence Platform

A full-stack situational-awareness platform for **Gujarat's public-health system**: ingests HMIS facility metrics, surfaces anomalies via ML + a rules engine, and exposes live alerts, forecasts, and policy-grounded Q&A through a React dashboard.

This repository ships three layers:

1. **Ingestion + Detection** — async FastAPI service that ingests facility metrics into TimescaleDB, runs an Isolation Forest anomaly detector and a rule-based engine, and ships `high`/`medium`/`low` severity alerts over WebSocket.
2. **RAG over policy PDFs** — ChromaDB-backed retriever indexed against 11 Indian public-health PDFs (TB, malaria, hypertension, Ayushman Bharat, NTEP, immunisation, maternal health, etc.) wired to a Groq/Ollama LLM via `backend/llm/synthesizer.py`.
3. **Intelligence UI** — Vite + React 19 + TypeScript SPA. Sidebar + top-bar shell, command palette (⌘K), executive Overview dashboard, Alerts / Investigations / Facilities / Analytics / AI Workspace / Reports / Settings pages, all built off the design tokens in `frontend/REDESIGN_SPEC.md`.

## Repository layout

```
hmis-inference/
├── backend/                # FastAPI + ML + RAG + LLM synthesis
│   ├── main.py             # entrypoint + lifespan + optional API-key gate
│   ├── database.py         # asyncpg pool + idempotent migration runner
│   ├── routers/            # 9 FastAPI routers (alerts, districts, qa, ..., websocket)
│   ├── llm/synthesizer.py  # Groq / Ollama provider with retries
│   ├── rag/                # embedder / ingest / retriever for the policy corpus
│   ├── ml/                 # anomaly.py, forecaster.py, risk_scorer.py
│   └── data/policy_docs/   # seeded RAG corpus (11 PDFs)
├── frontend/               # React 19 + TS + Vite + Tailwind + Leaflet + Recharts
│   ├── src/layouts/        # AppShell (Sidebar + TopBar inline)
│   ├── src/pages/          # one file per top-level route
│   ├── src/components/     # specialised components (AlertFeed, GujaratMap, ...)
│   ├── src/components/ui/  # Radix-wrapped primitives (button, dialog, tooltip, ...)
│   └── REDESIGN_SPEC.md    # design tokens + layout mockups
├── migrations/             # *.sql files, applied idempotently at backend boot
├── models/                 # pickled ML artifacts (gitignored)
├── scripts/                # seed_data, train_anomaly_model, ingest_policies
├── tests/                  # pytest suite (anomaly, rules, RAG, synthesizer, ...)
├── docker-compose.yml      # postgres(15) + redis + backend + celery worker/beat
├── Dockerfile
└── DEPLOY.md               # single-host deploy + nginx + certbot
```

## Quick start (local dev)

### Backend

```bash
cd hmis-inference
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # fill in GROQ_API_KEY if you want LLM synthesis
docker compose up -d postgres redis     # only the data services
uvicorn backend.main:app --reload --port 8000
```

On first boot the backend runs any pending SQL in `migrations/` (tracked in the `schema_migrations` table). Then load the seed data and the RAG corpus:

```bash
docker compose exec backend python scripts/seed_data.py        # 5 districts + 15 facilities
docker compose exec backend python scripts/seed_synthetic_data.py
docker compose exec backend python scripts/train_anomaly_model.py
docker compose exec backend python scripts/ingest_policies.py  # embed the PDFs
```

### Frontend

```bash
cd frontend
cp .env.example .env       # point VITE_API_BASE_URL at your backend
npm install
npm run dev                # http://localhost:5173
```

The SPA uses axios with a 120 s timeout for long-running LLM synthesis calls and forwards `VITE_API_KEY` as `X-API-Key` when it is set at build time.

## Docker / production

```bash
docker compose up -d --build
```

then point nginx at the published ports (`8000` for backend) and terminate TLS in front. See `DEPLOY.md` for the full nginx + certbot snippet and scaling notes.

## API surface

| Method + path | Purpose |
|---|---|
| `GET /health` | Detailed health (incl. LLM provider health) |
| `GET /api/v1/alerts/` | Filtered alert feed (severity, district, rule) |
| `POST /api/v1/alerts/{id}/ack` | Acknowledge an alert |
| `GET /api/v1/districts/risk-summary` | Per-district aggregated severity |
| `GET /api/v1/facilities/` | Facility directory |
| `POST /api/v1/ingest/` | Push facility metrics |
| `GET /api/v1/forecast/{district_id}` | 14-day OPD / ICU forecast |
| `GET /api/v1/insights/{alert_id}` | LLM-generated insight for an alert |
| `POST /api/v1/qa/` | RAG-grounded policy Q&A |
| `WS /ws/alerts/` | Live alert stream (Redis pub/sub fan-out) |

All `/api/v1/*` routes are gated by the optional `API_KEY` middleware when the env var is set.

## Testing

```bash
cd hmis-inference
python -m pytest tests/ -v
```

Coverage exists for `anomaly`, `rules_engine`, `risk_scorer`, the RAG retriever, the LLM synthesizer, the QA pipeline, and Celery tasks. Router, websocket, and frontend tests are not yet wired.

## Documentation

- `frontend/REDESIGN_SPEC.md` — design tokens, layout mockups, accessibility matrix
- `DEPLOY.md` — single-host deploy + nginx + certbot + scaling notes
- API specifics live in the docstrings of each router under `backend/routers/`
