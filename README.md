# Artem_Summer2026 — HMIS Intelligence Platform

Summer 2026 internship project: a situational-awareness platform for **Gujarat's public-health system** that ingests HMIS facility metrics, runs ML + rule-based detection, and exposes live alerts, forecasts, and policy-grounded Q&A through a React dashboard.

The deliverable is `internship_FIN.docx` plus a running HMIS demo.

## What's in this repository

| Path | Purpose |
|---|---|
| `hmis-inference/` | The shipped product — FastAPI backend + React 19 SPA + Postgres + Redis + ChromaDB. Self-contained; `docker compose up` runs the whole stack. |
| `hmis-inference/README.md` | Operator + dev quickstart for the product. |
| `hmis-inference/docs/ARCHITECTURE.md` | Layer contracts, data model, ops boundaries. |
| `hmis-inference/docs/API.md` | Full REST + WebSocket reference. |
| `hmis-inference/frontend/FRONTEND.md` | Page inventory, routing, design tokens. |
| `DONE.md` | What "shipped" means for this internship — scope decisions and known gaps. |
| `hmis-inference/requirements.txt` | Python backend deps. |
| `internship_FIN.docx` | Final internship report artefact. |
| `deploy.sh`, `deploy/` | Single-host nginx + certbot deploy helper. See `hmis-inference/DEPLOY.md` for the supported deploy path. |

## Getting the demo running

```bash
cd hmis-inference
docker compose up -d --build     # postgres + redis + backend
docker compose exec backend python scripts/seed_data.py
docker compose exec backend python scripts/train_anomaly_model.py
docker compose exec backend python scripts/ingest_policies.py
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

Full operator guide: `hmis-inference/DEPLOY.md`. API reference: `hmis-inference/docs/API.md`.

## Definition of done

See [`DONE.md`](./DONE.md) for the shipping target, scope decisions, and explicit non-goals.

## Local secrets

Copy `hmis-inference/.env.example` → `hmis-inference/.env` and `hmis-inference/frontend/.env.example` → `hmis-inference/frontend/.env`. Both are gitignored. Rotation guidance is inline in each `.env.example`. Heading straight to deploy? See `hmis-inference/DEPLOY.md §1.1`.

## Status as of 2026-06-26

ECC multi-agent scaffolding (`.agent/`, `.kilocode/`, `.opencode/`, the AGENTS*.md docs, `orchestrate.py`, `orchestration.log`) was stripped during the pre-deploy pass — it was never part of the HMIS shipping scope. See [`DONE.md`](./DONE.md) for the rationale and [`hmis-inference/DONE.md`](./hmis-inference/DONE.md) for product-specific shipping scope.
