-- Migration 003: inference_audit table for the 4-workstream inference system.
-- Every call to /api/v1/inference/* persists: workstream, trace_id, request,
-- response, severity, confidence, generated_at, expires_at. Used for the
-- weekly policy review called out in §6.2 of the intern scope.
-- 2026-06-27.

CREATE TABLE IF NOT EXISTS inference_audit (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream    VARCHAR(40) NOT NULL
        CHECK (workstream IN
            ('outbreak_risk', 'hospital_pressure', 'priority_rank', 'policy_memo')),
    trace_id      UUID        NOT NULL,
    district_id   UUID,
    facility_id   UUID,
    request       JSONB       NOT NULL,
    response      JSONB       NOT NULL,
    severity      VARCHAR(20)
        CHECK (severity IS NULL OR severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    confidence    DECIMAL(4,3)
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_inference_audit_workstream
    ON inference_audit(workstream);
CREATE INDEX IF NOT EXISTS idx_inference_audit_generated_at
    ON inference_audit(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_inference_audit_district_id
    ON inference_audit(district_id);
CREATE INDEX IF NOT EXISTS idx_inference_audit_facility_id
    ON inference_audit(facility_id);
