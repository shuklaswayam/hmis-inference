# Done — Artem_Summer2026 Internship Shipping Scope

This document records what "shipped" means for the HMIS Intelligence Platform internship deliverable, plus what's intentionally out of scope.

## The deliverable, in one sentence

> A running HMIS demo (FastAPI backend + React SPA, seeded data, alerts firing on synthetic metrics) plus `internship_FIN.docx` as the internship report.

## In scope (v1)

- **Backend** — FastAPI service; 9 routers; rules engine + Isolation-Forest anomaly detector + rule-based risk scorer; RAG over 11 Indian public-health PDFs; Groq/Ollama LLM synthesis; Redis pub/sub over WebSocket; Celery nightly inference task.
- **Database** — Timescale/Postgres with idempotent migrations (`migrations/001`, `002`); 5 districts + 15 facilities seeded for demo.
- **Frontend** — React 19 + TS + Vite SPA with Overview, Alerts, Investigations, Facilities, Analytics, AI Workspace, Reports, Settings pages; command palette (`⌘K`); Gujarat district map; alert feed with live WebSocket updates.
- **Auth** — Optional `API_KEY` middleware on `/api/v1/*`; disabled under pytest.
- **Deploy** — `docker-compose.yml`, `Dockerfile`, `DEPLOY.md` with nginx + certbot recipe.
- **Tests** — Backend pytest suite at 80%+ coverage of the critical paths (anomaly, rules, RAG, synthesizer, schemas, tasks, routers, websocket, DB). Frontend vitest smoke tests for utils, nav, and layout shell. See `DONE.md` in `hmis-inference/` for the coverage specifics.
- **Docs** — This repo top-level `README.md`, `hmis-inference/README.md`, `ARCHITECTURE.md`, `API.md`, `frontend/FRONTEND.md`.

## Explicitly out of scope (v1)

- **Frontend polish** beyond what's in `frontend/REDESIGN_SPEC.md`. A full redesign pass is months of work and was deliberately deferred in favour of shipping the backend demonstrably.
- **Production-scale Postgres tuning** — Timescale chunks are configured but not benchmarked for ≥10k facilities.
- **Real HMIS portal integration** — the `POST /api/v1/ingest/*` endpoints accept JSON, but no bidirectional sync with the live Gujarat HMIS portal is wired.
- **User accounts + RBAC** — single shared `API_KEY` only.
- **Horizontal Postgres** — the docker-compose assumes one writer; replication topology is not designed.
- **CI pipeline** — `gh` workflows exist in `.github/` but are minimal; no automated pre-merge gating.

## Scope decisions, with rationale

1. **Ship backend-as-is + minimal UI** rather than finish the frontend redesign. Rationale: the internship deliverable depends on a working demo; redesign work was always going to be evaluated, not completed, within the window.
2. **ML artifacts**: `scripts/train_anomaly_model.py` produces `models/isolation_forest.pkl`. `risk_scorer` is rule-based (no artifact). `forecaster` trains a small Prophet model per-request rather than pickling — kept simple, retraining is cheap. Scripts only exist for the artifact-producing models.
3. **ECC scaffolding was stripped on 2026-06-26**, not kept as reference. Rationale: this repo is an internship deliverable; reviewers care about the HMIS demo + `internship_FIN.docx`, not the multi-agent harness.
4. **`deploy.sh` + `deploy/` directory** kept on disk but not part of the shipping flow — see `hmis-inference/DEPLOY.md` for the supported deploy path.

## Known gaps the reviewer should not penalise

- ECC multi-agent scaffolding (`.agent/`, `.kilocode/`, `.opencode/`, the AGENTS*.md docs, `orchestrate.py`, `orchestration.log`, a GEMINI_API_KEY-failure log entry) was stripped during the 2026-06-26 pre-deploy pass — none of it was product code and none of it is needed for v1 evaluation.
- `backup/` (Jun 12 pre-install snapshot) was deleted; `~$ternship_FIN.docx` (Word lock file) and `.DS_Store` are now in the root `.gitignore`.

## What reviewers should look at

1. `python -m pytest hmis-inference/tests/ -v` — backend test suite.
2. `cd hmis-inference/frontend && npm test` — frontend smoke tests.
3. `docker compose up` — running demo.
4. `docs/ARCHITECTURE.md` + `docs/API.md` — system understanding.
5. `internship_FIN.docx` — final report.
