-- Migration 005: extract hot JSONB paths into typed columns on
-- inference_audit so weekly policy-review queries don't have to
-- descend into the JSONB blob every time.
--
-- Adds:
--   response_signals_count  INT      (len of signals / ranked / actions list)
--   response_top_tier       VARCHAR  (worst tier across items in the response)
--   response_llm_generated  BOOLEAN  (memo workstream only)
-- Plus an index on response_top_tier for the planner-style GROUP BY.
--
-- Deterministic backfill is run inline so the new columns are
-- populated for pre-existing rows immediately on migration.
-- 2026-06-30.

ALTER TABLE inference_audit
    ADD COLUMN IF NOT EXISTS response_signals_count INT,
    ADD COLUMN IF NOT EXISTS response_top_tier     VARCHAR(16),
    ADD COLUMN IF NOT EXISTS response_llm_generated BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_inference_audit_response_top_tier
    ON inference_audit(response_top_tier);

-- Backfill counts (cheap; just array length).
UPDATE inference_audit
SET    response_signals_count = CASE
           WHEN workstream IN ('outbreak_risk', 'hospital_pressure') THEN
               COALESCE(jsonb_array_length(response -> 'signals'), 0)
           WHEN workstream = 'priority_rank' THEN
               COALESCE(jsonb_array_length(response -> 'ranked'), 0)
           WHEN workstream = 'policy_memo' THEN
               COALESCE(jsonb_array_length(response -> 'recommended_actions'), 0)
           ELSE 0
       END
WHERE  response_signals_count IS NULL;

-- Backfill response_top_tier for outbreak/pressure (signals[i].tier).
UPDATE inference_audit AS a
SET    response_top_tier = sub.top_tier
FROM (
    SELECT id, UPPER(s->>'tier') AS top_tier
    FROM   inference_audit ia,
           LATERAL jsonb_array_elements(ia.response -> 'signals') s
    WHERE  ia.workstream IN ('outbreak_risk', 'hospital_pressure')
      AND  ia.response_top_tier IS NULL
      AND  s->>'tier' IS NOT NULL
    AND  UPPER(s->>'tier') IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW',
                                'STRAINED', 'NORMAL')
) AS sub
WHERE a.id = sub.id;

-- Backfill response_top_tier for priority_rank (ranked[i].severity).
UPDATE inference_audit AS a
SET    response_top_tier = sub.top_tier
FROM (
    SELECT DISTINCT ON (id) id, UPPER(r->>'severity') AS top_tier
    FROM   inference_audit ia,
           LATERAL jsonb_array_elements(ia.response -> 'ranked') r
    WHERE  ia.workstream = 'priority_rank'
      AND  ia.response_top_tier IS NULL
      AND  r->>'severity' IS NOT NULL
    ORDER  BY id,
             CASE UPPER(r->>'severity')
                 WHEN 'CRITICAL' THEN 4
                 WHEN 'HIGH'     THEN 3
                 WHEN 'MEDIUM'   THEN 2
                 WHEN 'LOW'      THEN 1
                 ELSE 0
             END DESC
) AS sub
WHERE a.id = sub.id;

-- Backfill memo llm_generated flag.
UPDATE inference_audit
SET    response_llm_generated = (response ->> 'llm_generated')::BOOLEAN
WHERE  workstream = 'policy_memo'
  AND  response_llm_generated IS NULL;
