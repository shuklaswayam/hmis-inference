HMIS Inference System — Implementation Plan

(4 focused workstreams, one FastAPI endpoint each, one dashboard widget each)

0. What the pivot demands — and what must change

┌─────────────────────────────────┬─────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────┐
│          Premise says           │               Today's system                │                           Required action                            │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│                                 │ 9 routers: alerts, districts, facilities,   │ Delete alerts, insights, qa, websocket. Replace with one new         │
│ One endpoint per workstream     │ forecast, ingest, insights, metrics, qa,    │ inference router exposing 4 endpoints. Keep districts, facilities,   │
│                                 │ websocket                                   │ forecast, ingest, metrics (used as data feeds).                      │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ Per (ward × disease) outbreak   │ Single-rule "outbreak" (R004) fires         │                                                                      │
│ risk with 4-tier label +        │ generically; no per-ward, no ML confidence  │ New module inference/outbreak_risk.py                                │
│ confidence                      │                                             │                                                                      │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ 48-hour pressure-tier           │ forecaster.py only does 7-day disease case  │ Extend forecaster or add a 48-h ICU/bed occupancy projection         │
│ projection per facility         │ forecasting, not 48-h facility load         │                                                                      │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ Top-5 ranked governance alerts  │ Existing risk_scorer.py returns 3-tier      │ New module inference/priority_rank.py with weighted multi-criteria   │
│ with owner                      │ priority, no ranking, no owner              │ scoring                                                              │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ Aggregated policy memo across   │ LLMSynthesizer.synthesize() is              │                                                                      │
│ WS 1–3 (different prompt than   │ single-purpose, no memo prompt              │ New module inference/policy_memo.py with separate prompt             │
│ per-facility insight)           │                                             │                                                                      │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ 15-min Redis refresh, log every │ Alerts uses 60 s Redis cache; no            │ New cache layer (TTL=900), new inference_audit table, new dashboard  │
│  inference output, 4 widgets,   │ inference-audit table; no widgets           │ widgets                                                              │
│ collapsible memo panel          │                                             │                                                                      │
├─────────────────────────────────┼─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
│ "Health Commissioner Dashboard" │ Today the entry is generic OverviewPage     │ New HealthCommissionerDashboard.tsx (or repurpose OverviewPage)      │
│  with 4 new widgets             │ (alerts feed + KPI tiles)                   │                                                                      │
└─────────────────────────────────┴─────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘

▎ Pivots precedence: the user's framing is the binding constraint. The premise overrides the existing alerting posture, aurora "recent alerts" feature, freeform chat, and the unified /insights/{id} endpoint will be retired.

---
1. Architecture changes (high-level)

backend/
├── inference/                          ← NEW PACKAGE (this is the system)
│   ├── __init__.py
│   ├── outbreak_risk.py                ← Workstream 1
│   ├── hospital_pressure.py            ← Workstream 2
│   ├── priority_rank.py                ← Workstream 3
│   ├── policy_memo.py                  ← Workstream 4 (aggregator)
│   ├── audit.py                        ← writes to inference_audit table
│   └── cache.py                        ← 15-minute Redis helpers (read-through, write-around)
├── ml/
│   ├── forecaster.py                   (keep — also add 48-h facility-load forecaster)
│   └── outbreak_classifier.py          ← NEW (DecisionTree / LogReg trained on HMIS history)
├── llm/
│   └── memo_synthesizer.py             ← NEW (different prompt, JSON output {headline, body, actions[]})
├── routers/
│   ├── inference.py                    ← NEW: 4 endpoints, one per workstream
│   ├── ... (kept routers unchanged)
│   └── _legacy/                        ← (move/delete) alerts.py, insights.py, qa.py, websocket.py
├── database.py                         (unchanged)
└── main.py                             (register only the new router; remove retired routers)

frontend/src/
├── pages/
│   └── HealthCommissionerDashboard.tsx ← NEW (4 widgets + memo panel)
├── components/dashboard/
│   ├── OutbreakRiskWidget.tsx           ← NEW (WS1)
│   ├── HospitalPressureWidget.tsx       ← NEW (WS2)
│   ├── PriorityRankWidget.tsx           ← NEW (WS3)
│   ├── PolicyMemoPanel.tsx              ← NEW (WS4; collapsible executive memo)
│   └── WidgetShell.tsx                  ← Shared card chrome (severity badge, freshness timestamp, 1-line action)
├── api/client.js                        (extend with /api/v1/inference/* calls)
└── router.tsx                           (replace index route → HealthCommissionerDashboard)

---
2. Four workstream modules (the core)

Workstream 1 — Outbreak Risk Scorer (inference/outbreak_risk.py)

Inputs: disease_reports (last 14 d) per (district, disease) + baseline avg from prior 30 d.
Logic (rule-augmented scoring — per the premise):
- Threshold rules (deterministic, ported from R004 with per-ward + per-disease granularity):
  - cases ≥ 2× baseline → ≥ Medium
  - cases ≥ 4× baseline OR deaths > 0 → High
  - ≥ 5× baseline OR deaths ≥ 3 → Critical
  - otherwise Low
- ML classifier for confidence: DecisionTreeClassifier (or LogisticRegression) trained on HMIS historical bucket→tier labels, with features:
[cases_last_7d, cases_baseline_ratio, deaths_last_7d, weekly_trend_slope, district_z_score]
- Output: {ward_id, disease, tier ∈ {Low, Medium, High, Critical}, confidence ∈ [0,1], baseline_ratio, contributing_signals[], recommended_action, one_liner, generated_at}
- Confidence = classifier soft-probability × a small seasonality multiplier (JAS-OMC window for vector-borne diseases).

Workstream 2 — Hospital Pressure Classifier (inference/hospital_pressure.py)

Inputs: facility_metrics (98 facilities in seed; would be 256 per premise's wider scope — code is facility-count-agnostic). Inputs are: bed_occupancy_pct, icu_occupancy_pct, opd_visits, emergency_visits, wait-time proxy (emergency_visits / staffed_beds if available).
Logic:
- Tier rules (deterministic):
  - icu≥90 OR bed≥95 OR (opd_visits ≥ 1.8× avg AND icu≥75) → Critical
  - icu≥80 OR bed≥85 OR opd_visits ≥ 1.5× avg → Strained
  - else Normal
- 48-hour trend projection: lightweight forecaster (extend ml/forecaster.py → forecast_facility_load(facility_id, horizon_days=2) using Prophet) → returns a {icu_pct_pred_24h, icu_pct_pred_48h, bed_pct_pred_48h, ICU_pressure_trend ∈ {rising, stable, easing}}.
- Output: {facility_id, tier, proj_48h, contributing_metrics[], recommended_action, one_liner, generated_at}.

Workstream 3 — Priority Alert Ranker (inference/priority_rank.py)

Input: all current inference_results rows (severity + inference_type) plus a small attached metadata bundle: severity weight = {CRITICAL: 6, HIGH: 4, MEDIUM: 2, LOW: 1}. Each candidate signal is scored by:
score = severity_w × 0.55
      + recency_h × 0.25       # 1/(hours_old+1), normalized
      + spread    × 0.20       # number of facilities/diseases this event affects
      + owner_penalty          # +1 if no owner assigned (forces human triage)
- Top-5 surfaced with: rank, headline, severity_score ∈ [0,10], recommended_owner (state/district/facility head), sla_hours, evidence_refs[]. Owner is inferred deterministically:
  - maternal_deaths → District Maternal Health Officer
  - icu_overload / severe_stockout → Facility In-Charge + State Procurement
  - outbreak(rank≥High) → District Surveillance Officer + State Health Commissioner (escalation)
  - zero-dose → Immunisation Officer
- Audit: every ranked list is written row-wise to inference_audit.

Workstream 4 — Policy Insight Narrator (inference/policy_memo.py + llm/memo_synthesizer.py)

Aggregator contract: the memo endpoint takes the fresh cached outputs of WS 1, 2, 3 (read-through Redis, no recompute). It builds a single KPIBundle JSON:
{
  "outbreak_top":   [ {ward, disease, tier, confidence, one_liner} × ≤3 ],
  "pressure_top":   [ {facility, tier, proj_48h, one_liner}      × ≤3 ],
  "priority_top5":  [ {rank, headline, severity_score, owner}     × 5 ],
  "district_kpis":  {district → {opd, icu, maternal, immunisation}},
  "generated_at":   ISO,
  "context_window":  "last 14 days"
}
- Synthesizer (llm/memo_synthesizer.py) is separate from the per-facility LLMSynthesizer because the prompt contract differs:
  - System prompt: "You are a Policy Insight Narrator for the Gujarat Health Commissioner. Output JSON: {headline, body_md, recommended_actions: [{action, owner, sla_hours}]}. Each action must reference a specific item in priority_top5. Do not invent. ≤ 350 words."
  - Temperatures: temperature=0.2, max_tokens=900.
  - JSON validated; falls back to a structured template (no LLM) on failure.
- Output: rendered plain-English memo + structured action list. Cached 15 min.

---
3. API contract — routers/inference.py (4 endpoints)

┌────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────┬───────────────────┬───────┐
│                             Method + path                              │                  Purpose                   │     Cache key     │  TTL  │
├────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┼───────────────────┼───────┤
│ GET /api/v1/inference/outbreak-risk?disease=&district=                 │ WS1: per (ward, disease) tier + confidence │ inf:outbreak:v1:* │ 900 s │
├────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┼───────────────────┼───────┤
│ GET /api/v1/inference/hospital-pressure?facility_id= (or district_id=) │ WS2: tier + 48-h projection per facility   │ inf:pressure:v1:* │ 900 s │
├────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┼───────────────────┼───────┤
│ GET /api/v1/inference/priority-rank                                    │ WS3: top-5 ranked list                     │ inf:rank:v1       │ 900 s │
├────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┼───────────────────┼───────┤
│ GET /api/v1/inference/policy-memo                                      │ WS4: narrate memo from WS1+2+3             │ inf:memo:v1       │ 900 s │
└────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────┴───────────────────┴───────┘

Response envelope (consistent across all 4):
{
  "data":        { … workstream-specific result … },
  "confidence":  0.83,                    // 0..1 (or per-item for ranked list)
  "severity":    "HIGH",                  // LOW | MEDIUM | HIGH | CRITICAL
  "generated_at":"2026-06-27T18:14:00Z",
  "expires_at":  "2026-06-27T18:29:00Z",
  "trace_id":    "uuid"
}

Cache layer (inference/cache.py):
- Read-through: await cache_get_or_set(key, ttl=900, loader=…).
- Write-around on every endpoint, with expires_at mirrored in DB on audit.
- Celery beat job (existing tasks.py infrastructure) refreshes each key 1 minute before TTL expiry on dashboard warm-up.

Audit logging (inference/audit.py):
- Every endpoint call persists a row to inference_audit (new migration 003_inference_audit.sql):
CREATE TABLE inference_audit (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream    VARCHAR(40) NOT NULL,   -- outbreak_risk | hospital_pressure | priority_rank | policy_memo
    trace_id      UUID NOT NULL,
    request       JSONB NOT NULL,
    response      JSONB NOT NULL,
    severity      VARCHAR(20),
    confidence    DECIMAL(4,3),
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ
);
- Auditor can run SELECT workstream, severity, COUNT(*) FROM inference_audit WHERE generated_at >= NOW() - INTERVAL '7 days' GROUP BY 1,2 for the weekly review cited in the premise.

---
4. Data pipeline (per §6.2 of the premise)

- Ingest: unchanged (POST /api/v1/ingest/*); the inference layer is read-side only over facility_metrics, disease_reports, inference_results, districts, health_facilities.
- Normalisation: a single _normalize_metrics(), _normalize_diseases() helper inside inference/cache.py handles NULL coercion, stale-record (≥14-day last-reported → mark confidence low), and outlier handling (clip icu/bed to [0,100]).
- Validation: Pydantic models for every internal computation result — never raw dicts leak across the network.
- Caching policy: consistent 15-min TTL. Refresh cycle is enforced by setting expires_at = generated_at + 900s everywhere; clients can poll expectations.
- Audit logging: every inference output persisted (above).

---
5. Dashboard integration — HealthCommissionerDashboard.tsx

Route at / (replacing the current OverviewPage). Four widgets rendered in a 2×2 bento grid; memo panel pinned below or, on ≤lg viewports, in a collapsible executive summary drawer.

Each widget obeys a shared <WidgetShell>:

┌──────────────────────────────────────────────┐
│ [Title]            [Severity badge] [• live] │
│ Last updated: 2 min ago                       │
│ ─ one-line recommended action ─              │
│ ─ summary block (varies per workstream) ─     │
│ [Confidence: 0.83]   [Trace → detail]         │
└──────────────────────────────────────────────┘
- Refetch cadence: every 5 min (useQuery({staleTime: 5*60*1000, refetchInterval: 5*60*1000})); the cache TTL is 15 min on the server, so 5-min refetch is safe and gives the freshness stamp the premise demands.
- Loading/error/disclosure: skeletons, retry button, and "data older than 15 min" stale warning handled per-widget.
- Memo panel (PolicyMemoPanel): collapsible (details/summary + framer-motion spring expand). Renders headline, the markdown body_md, and the typed recommended_actions[] (each row: action • owner • SLA). A "Regenerate" button forces the endpoint to bypass cache.

Widget specifics

┌────────────────────────┬────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
│         Widget         │                         Visualised fields                          │                         Notes                          │
├────────────────────────┼────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ OutbreakRiskWidget     │ Table: ward • disease • tier • 1-line action. Filter pills: All /  │ Top 3 of each tier; if Critical present, an alert      │
│                        │ Dengue / Malaria / etc.                                            │ ribbon bar                                             │
├────────────────────────┼────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ HospitalPressureWidget │ Bar list per facility with current + 48-h projection twin bars.    │ Tier-coloured badges; click → facility drill-down      │
│                        │ Trend chevron: ▲ rising, ▼ easing, ◆ stable.                       │ (reuses FacilitiesPage route)                          │
├────────────────────────┼────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ PriorityRankWidget     │ Numbered list 1→5: rank, headline, severity chip, owner pill, SLA  │ Click action → memo jump-link                          │
│                        │ chip                                                               │                                                        │
├────────────────────────┼────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ PolicyMemoPanel        │ Top-level collapsible; sub-actions in ranked list inside; "share   │ Refetch is manual by default so the Commissioner       │
│                        │ via clipboard"                                                     │ doesn't get competing regenerations                    │
└────────────────────────┴────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────┘

---
6. Deletion / deprecation list

The premise explicitly says "I don't need an alerts system." Following CLAUDE.md ("Before deleting or overwriting, look at the target"), validated repurposing:

┌────────────────────────────────────────────────┬────────────────────────────────────────────────────┬────────────────────────────────────────────────┐
│                   Component                    │                      Decision                      │                     Reason                     │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│                                                │ Move to routers/_legacy/alerts.py; keep            │ "Alerts system" is replaced by WS3 in spirit;  │
│ routers/alerts.py (HIGH/MEDIUM/LOW feed)       │ routers/alerts.py as a thin proxy resolving to     │ doesn't force a frontend reroute               │
│                                                │ priority-rank                                      │                                                │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ routers/insights.py (per-facility unified      │ Delete (per-facility insight is not in the         │ Premise is workload-of-4, not per-facility     │
│ insight)                                       │ 4-workstream brief)                                │                                                │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ routers/qa.py +                                │                                                    │ Out of scope; both linger on disk but are not  │
│ backend/rag/ingest.py/retriever.py (freeform   │ Retire RAG/Q&A from the inference system           │ mounted by main.py                             │
│ Q&A + RAG)                                     │                                                    │                                                │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ WS /ws/alerts/                                 │ Disable router                                     │ Inference is request/response, not streaming   │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ frontend/AIChat.tsx, AIPage.tsx "Ask Artem"    │ Replace with PolicyMemoPanel widget                │ Same ⟨headline, why, action⟩ contract, but     │
│ widget                                         │                                                    │ served by /api/v1/inference/policy-memo        │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ OverviewPage's "Live Telemetry Alert Feed"     │ Replace with PriorityRankWidget                    │ Engage AlertsPage only as a drill-through      │
│                                                │                                                    │ detail; no live feed                           │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│                                                │ Keep column but write only when WS2/per-facility   │                                                │
│ inference_results.llm_generated boolean        │ context is reused; memo writes go to               │ Schema stays backward-compatible               │
│                                                │ inference_audit                                    │                                                │
├────────────────────────────────────────────────┼────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│ risk_scorer.py                                 │ Reuse its severity→priority mapping inside         │ The math is fine; we're giving it a role       │
│                                                │ priority_rank.py                                   │ rather than inventing new logic                │
└────────────────────────────────────────────────┴────────────────────────────────────────────────────┴────────────────────────────────────────────────┘

▎ Per the user's framing ("strictly follow this"), deletions are inside this list. Anything not listed = unchanged.

---
7. File-level build order (1-pass where possible)

I'll use a "permit-to-build" sequence — each pass closes a slice that's testable in isolation.

1. Migration 003_inference_audit.sql + register in database.py's idempotent runner. (read-side only; safe.)
2. backend/inference/__init__.py, cache.py, audit.py, schemas (Pydantic). (No behaviour yet — just utilities.)
3. Workstream 1 — outbreak_risk.py (rules + ML classifier), ml/outbreak_classifier.py (train script + persisted model).
4. Workstream 2 — hospital_pressure.py; extend ml/forecaster.py with forecast_facility_load(48h).
5. Workstream 3 — priority_rank.py (pure function — rank list, owner inference, no DB write beyond audit).
6. Workstream 4 — policy_memo.py + llm/memo_synthesizer.py.
7. Router — routers/inference.py exposing the 4 endpoints with the cache + audit wrapper.
8. Wire main.py: register inference router; quarantine legacy routers.
9. Frontend widgets in this order: WidgetShell → OutbreakRiskWidget → HospitalPressureWidget → PriorityRankWidget → PolicyMemoPanel → HealthCommissionerDashboard.tsx → router.tsx swap.
10. Retire AIPage / AIChat (route removed, file unregistered).
11. Tests (each module has unit + integration per CLAUDE.md):
  - tests/test_inference_outbreak_risk.py (golden inputs → tier; classifier confidence)
  - tests/test_inference_hospital_pressure.py (rules + 48-h projection)
  - tests/test_inference_priority_rank.py (ordering, owner mapping, top-5 invariant)
  - tests/test_inference_policy_memo.py (cache hit, cache fallback, LLM failure path → structured template)
  - tests/test_inference_router.py (HTTP shape per endpoint)
  - Update tests/conftest.py with client fixture + Redis stub
12. Documentation: rewrite README.md with the 4-workstream surface and a DONE.md addendum. Keep DEPLOY.md.

---
8. Key technical decisions (one line each)

- ML for WS1: scikit-learn DecisionTreeClassifier (≤5 features) is interpretable and serializable (joblib.dump) — same artefact style as the existing isolation_forest.pkl. Confidence = leaf-class probability.
- 48-h forecaster: Prophet on facility_metrics per facility, with horizon_days=2, weekly seasonality on/off by sample-size heuristic. Standalone, not an extension in the existing 7-day disease forecaster.
- Owner mapping: static dict in priority_rank.py (source-of-truth lives in code; can move to policy_documents later).
- Memo cache invalidation: whenever WS3's ranked list changes, the memo's cache key gets a rev=N suffix; otherwise hit comes back in O(1).
- Audit volume: expected ≤ ~5k rows / week with the 15-min cadence. Table is append-only with (workstream, generated_at DESC) index — no partitioning needed in scope.
- Auth: keep the existing optional APIKeyGate — /api/v1/inference/* falls under its blanket.
- Frontend refresh: 5 min default; the memo panel's Regenerate bypasses cacheclient-side.
r
---
9. What this delivers against the premise is

┌─────────────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
│                                       Premise clause                                        │                      Delivered by                      │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "6.1 Rule-augmented scoring for Outbreak Risk & Hospital Pressure"                          │ outbreak_risk.py (rules+ML), hospital_pressure.py      │
│                                                                                             │ (rules+ML)                                             │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "Ranking model for Priority Alert Ranker"                                                   │ priority_rank.py (weighted severity × recency ×        │
│                                                                                             │ spread)                                                │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "LLM inference for Policy Insight Narrator"                                                 │ policy_memo.py + llm/memo_synthesizer.py               │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "FastAPI inference server exposing four endpoints"                                          │ routers/inference.py (4 endpoints)                     │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "6.2 Ingest via REST or DB → normalise → 15-min Redis refresh → log with timestamps"        │ inference/cache.py (TTL 900 s + expires_at) +          │
│                                                                                             │ inference/audit.py                                     │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "6.3 Four inference widgets with current output, confidence/severity, last-updated          │ HealthCommissionerDashboard.tsx + 4 widgets using      │
│ timestamp, one-line recommended action"                                                     │ WidgetShell                                            │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "Policy memo widget renders the LLM-generated narrative in a collapsible executive summary  │ PolicyMemoPanel.tsx (collapsible via <details>/Framer  │
│ panel"                                                                                      │ collapse)                                              │
├─────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Workstream mappings                                                                         │ See table in §0/§5                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────┘

---
10. Open items flagged for confirmation

Per CLAUDE.md, I avoid asking when the path is obvious. Two points that aren't obvious from the premise alone, and worth your confirmation before code is written:

1. Legacy Q&A mood: Should the /api/v1/ask RAG-grounded policy question endpoint be deleted entirely, preserved as a bonus page, or retained but kept out of the dashboard?
2. Facility count: the premise quotes "256 facilities". The current seed data has 15 across 5 districts. Do you want me to (a) ship the 15-facility scope as a v1 proof and keep the inference logic facility-count-agnostic, or (b) generate synthetic facility rows up to 256 first?

Everything else is unambiguous and ready to implement. When you're ready, I'll start with pass 1 (migration 003_inference_audit.sql + base package) and proceed through the 12-step build order above.