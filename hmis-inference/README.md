# HMIS Inference Platform

A four-workstream inference service for Gujarat's public-health system.
Given HMIS facility metrics and disease reports, the platform produces
the four policy-facing outputs called out in the internship scope:

| # | Workstream                | Output                                                              |
|---|---------------------------|---------------------------------------------------------------------|
| 1 | **Outbreak Risk**         | 4-tier (Low / Medium / High / Critical) per (ward × disease) + confidence |
| 2 | **Hospital Pressure**     | 3-tier (Normal / Strained / Critical) per facility + 48-hour projection |
| 3 | **Priority Rank**         | Top-5 ranked policy actions for the Commissioner, with owner + SLA |
| 4 | **Policy Memo**           | LLM-narrated daily brief across the other three workstreams         |

Each workstream is exposed as its own FastAPI endpoint, cached through
Redis with a 15-minute TTL, and audited row-wise in `inference_audit`.

```
hmis-inference/
├── backend/
│   ├── inference/             ← NEW: the 4 workstream modules
│   │   ├── outbreak_risk.py       (WS1)
│   │   ├── hospital_pressure.py   (WS2)
│   │   ├── priority_rank.py       (WS3)
│   │   ├── policy_memo.py         (WS4, aggregator)
│   │   ├── cache.py               (15-min Redis helpers)
│   │   ├── audit.py               (inference_audit writer)
│   │   └── schemas.py             (Pydantic envelopes)
│   ├── llm/
│   │   ├── synthesizer.py         (legacy per-facility insight)
│   │   └── memo_synthesizer.py    (NEW: WS4 memo prompt + fallback)
│   ├── ml/
│   │   ├── forecaster.py          (DiseaseForecaster + FacilityLoadForecaster)
│   │   ├── risk_scorer.py         (kept for back-compat)
│   │   ├── anomaly.py             (kept)
│   │   └── outbreak_classifier.py (NEW: WS1 DecisionTree classifier)
│   ├── routers/
│   │   ├── inference.py           (4 workstream endpoints)
│   │   ├── districts.py           (kept)
│   │   ├── facilities.py          (kept)
│   │   ├── forecast.py            (kept)
│   │   ├── ingest.py              (kept)
│   │   └── metrics.py             (kept)
│   ├── _legacy/                   (alerts / insights / qa / websocket now retired)
│   └── main.py                    (registers /api/v1/inference/*)
├── frontend/
│   └── src/
│       ├── pages/
│       │   └── HealthCommissionerDashboard.tsx  (NEW root page)
│       └── components/dashboard/
│           ├── WidgetShell.tsx
│           ├── OutbreakRiskWidget.tsx
│           ├── HospitalPressureWidget.tsx
│           ├── PriorityRankWidget.tsx
│           └── PolicyMemoPanel.tsx
├── migrations/
│   ├── 001_create_tables.sql
│   ├── 002_add_metrics_severity_columns.sql
│   └── 003_inference_audit.sql       (NEW)
├── scripts/
│   ├── seed_data.py                 (256 facilities, replaces 15-facility seed)
│   ├── seed_synthetic_data.py
│   ├── train_anomaly_model.py
│   ├── train_outbreak_classifier.py (NEW)
│   └── ingest_policies.py
└── tests/
    ├── test_inference_outbreak.py
    ├── test_inference_pressure.py
    ├── test_inference_priority.py
    ├── test_inference_memo.py
    └── test_inference_router.py
```

## Quick start (local dev)

```bash
cd hmis-inference
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # fill in GROQ_API_KEY for the memo synthesizer
docker compose up -d postgres redis
uvicorn backend.main:app --reload --port 8000
```

On first boot the backend runs any pending SQL in `migrations/` (tracked in
`schema_migrations`). Then seed:

```bash
python scripts/seed_data.py                # 5 districts + 256 facilities
python scripts/seed_synthetic_data.py      # 90 days of metrics + disease reports
python scripts/train_anomaly_model.py      # isolation forest for legacy alerts
python scripts/train_outbreak_classifier.py # WS1 classifier
```

## API surface

| Method + path                                | Purpose                                                                    |
|----------------------------------------------|----------------------------------------------------------------------------|
| `GET /health`                                | Service health + active LLM provider                                       |
| `GET /health` (legacy)                       | Now returns the 4-workstream list                                          |
| `GET /api/v1/inference/health`               | Inference subsystem health                                                 |
| `GET /api/v1/inference/outbreak-risk`        | WS1: tiered outbreak signals (per district × disease)                      |
| `GET /api/v1/inference/hospital-pressure`    | WS2: facility tier + 48-hour projection                                    |
| `GET /api/v1/inference/priority-rank`        | WS3: top-5 ranked policy actions                                           |
| `GET /api/v1/inference/policy-memo`          | WS4: LLM-narrated memo (aggregates WS1 + WS2 + WS3)                        |
| `GET /api/v1/districts/`                     | List districts                                                             |
| `GET /api/v1/facilities/`                    | Facility directory                                                         |
| `GET /api/v1/forecast/{disease}`             | 7-day Prophet disease forecast                                             |
| `GET /api/v1/metrics/trend`                  | Daily metric trend for a facility                                          |
| `POST /api/v1/ingest/{district,disease_report,facility_metrics}` | Ingest HMIS data                                                |

All `/api/v1/*` routes are gated by the optional `API_KEY` middleware when the
env var is set.

## Response envelope

Every inference endpoint returns the same shape:

```json
{
  "workstream":  "outbreak_risk",
  "data":        { … },
  "severity":    "HIGH",
  "confidence":  0.83,
  "generated_at":"2026-06-27T18:14:00Z",
  "expires_at":  "2026-06-27T18:29:00Z",
  "trace_id":    "uuid",
  "cache_hit":   true
}
```

## Caching & audit

* 15-minute Redis TTL (`INFERENCE_CACHE_TTL_SECONDS`, defaulted to 900).
* Every call persists one row in `inference_audit` (`workstream`, `trace_id`,
  `request`, `response`, `severity`, `confidence`, `generated_at`,
  `expires_at`). Weekly policy review is a SQL
  `GROUP BY workstream, severity` away.

## Environment variables

Every variable below is optional — defaults are picked when a key is
absent. `.env.example` is the canonical inventory; the table here is
the on-the-run reference.

| Variable | Used by | Default | Notes |
|----------|---------|---------|-------|
| `DATABASE_URL` | Backend, scripts | `postgresql://hmis:hmis_password@localhost:5432/hmis` | asyncpg-style URL |
| `REDIS_URL` | Backend, Celery | `redis://localhost:6379/0` | 15-min cache + pub/sub |
| `ALLOWED_ORIGINS` | Backend CORS | `http://localhost:5173,http://localhost:5174` | Comma-separated |
| `JWT_SECRET` | Backend auth | dev fallback `artem-dev-secret-…` | Set real value in prod |
| `JWT_TTL` | Backend auth | `14400` (4 h) | Access-token lifetime |
| `JWT_REFRESH_TTL` | Backend auth | `604800` (7 d) | Refresh-token lifetime |
| `API_KEY` | Backend auth | unset | Legacy header (see `DEPRECATION.md`) |
| `LLM_PROVIDER` | WS4 synthesizer | `ollama` | `groq` or `ollama` |
| `GROQ_API_KEY` | WS4 synthesizer | unset | Required when `LLM_PROVIDER=groq` |
| `GROQ_MODEL` | WS4 synthesizer | `llama-3.3-70b-versatile` | |
| `OLLAMA_MODEL` | WS4 synthesizer | `mistral` | |
| `OLLAMA_BASE_URL` | WS4 synthesizer | `http://localhost:11434` | |
| `INFERENCE_CACHE_TTL_SECONDS` | Cache layer | `900` | 15 minutes |
| `INFERENCE_WARM_INTERVAL_SECONDS` | Celery beat | `840` | 14 minutes (cache-warm cadence) |
| `AUDIT_TTL_DAYS` | Retention | `90` | Hot → archive boundary |
| `WEBHOOK_URL` | Notifier | unset | POST destination on CRITICAL transitions |
| `WEBHOOK_ENABLED` | Notifier | `0` | `1` enables the URL above |
| `WEBHOOK_TIMEOUT_S` | Notifier | `5.0` | POST timeout |
| `PERF_SMOKE` | Test runner | `0` | `1` activates `tests/test_perf_smoke.py` |
| `HMIS_VERSION` | `/health` | `2.0.0` | |
| `VITE_API_BASE_URL` | Frontend dev | `http://localhost:8000` | |
| `VITE_API_KEY` | Frontend build | unset | Mirrors `API_KEY` at SPA build time |

## Dashboard

`/` is the **Health Commissioner Dashboard** — a 2×2 widget bento:

* Outbreak Risk widget
* Hospital Pressure widget (with 48-h projection icons)
* Priority Actions (top 5 ranked items with owner + SLA)
* Daily Brief placeholder (the collapsible Policy Memo panel sits below)

The collapsible memo panel renders the headline, markdown body, and the
typed action list (action · owner · SLA) and a copy-to-clipboard button.

## Testing

```bash
pytest tests/test_inference_*.py -v
```

Pure-Python tests cover the tier rules, scoring, owner dispatch, and the
deterministic fallback template. Router tests use mocked `Database` and
`Redis` so the suite runs without Postgres.

## Docker / production

```bash
docker compose up -d --build
```

then point nginx at the published ports. See `DEPLOY.md` for the full
recipe.
