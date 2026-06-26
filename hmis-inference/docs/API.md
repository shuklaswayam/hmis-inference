# API Reference — HMIS Inference

All endpoints exposed by `backend/main.py`. FastAPI auto-generates an interactive OpenAPI doc at **`/docs`** when the service is running; this file mirrors that with extra operator context.

- Base path prefix: `/api/v1/*` (gated by optional `API_KEY` middleware); the `/` and `/health` paths are open.
- All bodies are JSON; ISO-8601 for timestamps; Postgres UUID strings for IDs.
- Errors: `4xx` for client errors, `5xx` for server. `422` = Pydantic validation failed (auto body), `400` = explicit validation in handler, `404` = not found, `401` = API key missing/mismatch.

## Health

| Method | Path | Notes |
|---|---|---|
| `GET` | `/` | Liveness. Returns `{"status":"ok","service":"hmis-inference"}`. |
| `GET` | `/health` | Detailed health — also reports LLM provider health and whether auth is enabled. |

## `/api/v1/alerts/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/alerts/` | Run the rules engine on latest facility metrics; persist new triggers; return active (non-expired) alerts filtered by `district_id` and `severity`. Response cached in Redis for 60 s. |

Query params: `district_id` (UUID, optional), `severity` (`HIGH` / `MEDIUM` / `LOW`, default `HIGH`).

Side effect: HIGH-severity alerts are published to Redis channel `new_alerts` for WebSocket fan-out.

## `/api/v1/districts/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/districts/` | Static district directory (id, name, state, population, zone). |
| `GET` | `/api/v1/districts/risk-summary` | Per-district aggregated severity sorted HIGH → MEDIUM → LOW → NONE. |

## `/api/v1/facilities/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/facilities/` | Facility directory joined with latest metric per facility. |
| `GET` | `/api/v1/facilities/summary` | Aggregate: total facilities, total districts, total beds, total ICU beds, avg bed/ICU occupancy, total OPD, total emergency visits. |

## `/api/v1/ingest/`

Three ingestion endpoints, one per entity. Validated by Pydantic models in `backend/schemas.py`; `422` on schema failure.

| Method | Path | Body |
|---|---|---|
| `POST` | `/api/v1/ingest/district` | `DistrictCreate` — `{name, state, population, zone?}` |
| `POST` | `/api/v1/ingest/disease_report` | `DiseaseReportCreate` — `{disease_name, facility_id, reported_date, case_count}` |
| `POST` | `/api/v1/ingest/facility_metrics` | `FacilityMetricsCreate` — daily facility numbers |

Returns the inserted row with server-generated UUID.

## `/api/v1/forecast/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/forecast/{district_id}` | 14-day OPD / ICU forecast. Returns `404` if no historical data, `400` if fewer than 14 days are available. |

The district id is the disease slug used in `disease_reports.disease_name`, not a UUID.

## `/api/v1/insights/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/insights/{facility_id}` | LLM-generated narrative for a facility's most recent flagged state. `404` when no metrics exist for the facility. |

Runs the full `Rule → Anomaly → RiskScorer → Forecast → LLM` pipeline. Latency is dominated by the LLM call (5–15 s); falls back to deterministic narrative when LLM is offline.

## `/api/v1/metrics/`

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/metrics/trend` | Time-series for one numeric metric on one facility. `400` on invalid metric name. |

Query params: `facility_id` (UUID), `metric` (one of `opd_visits`, `icu_occupancy_pct`, `bed_occupancy_pct`, `emergency_visits`, `maternal_deaths`, `deliveries`), `days` (int, default 7).

## `/api/v1/ask`

| Method | Path | Body |
|---|---|---|
| `POST` | `/api/v1/ask` | `AskRequest` — `{query, district_id?}` |

Policy-grounded Q&A: retrieves top-5 Chroma chunks, gathers 7-day district metrics + last 10 active alerts, calls Groq/Ollama to answer. Response cached 5 min in Redis.

> **Note:** the OpenAPI tag is `qa`, but the path is `/api/v1/ask` (matches `tests/test_routers.py::test_all_routers_present_in_app`). The README mentions `/api/v1/qa/` — that's stale and will be corrected; the router prefix is `/api/v1` and the path inside is `/ask`.

Response shape (`AskResponse`): `{question, answer, sources, district_id, timestamp}`.

## WebSocket

| Method | Path | Notes |
|---|---|---|
| `WS` | `/ws/alerts` | Live fan-out of `new_alerts` Redis channel. No auth — terminate in front of it (nginx + TLS + upstream API key check). |

Frame payload: `{type: "new_alert", alert: {id, facility_id, district_id, facility_name, severity, rule_name, what_is_happening, created_at}}`.

## Auth

Set `API_KEY` in the backend env to enable. All `/api/v1/*` paths then require `X-API-Key` (or `Authorization: Bearer <key>`). Tests run under pytest regardless (auto-skipped via `PYTEST_CURRENT_TEST` env var).

## CORS

`ALLOWED_ORIGINS` env (comma-separated). Defaults to `http://localhost:5173` and `http://localhost:5174` for local dev. The frontend SPA must be in the allow-list.

## 422 vs 400

- `422 Unprocessable Entity` is FastAPI/Pydantic's automatic response when request body fails schema validation (missing required fields, wrong types). The body lists each field error.
- `400 Bad Request` is raised explicitly inside handlers when the request is well-formed but semantically wrong (unknown metric name, too little historical data).
