-- Migration 004: users table + RBAC fields + audit archive + per-row user_id.
-- 2026-06-28.

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    full_name     VARCHAR(255) NOT NULL,
    hashed_password TEXT NOT NULL,
    role          VARCHAR(32) NOT NULL CHECK (role IN
        ('COMMISSIONER', 'STATE_OFFICER', 'DISTRICT_OFFICER', 'FACILITY_HEAD', 'VIEWER')),
    district_id   UUID REFERENCES districts(id) ON DELETE SET NULL,
    facility_id   UUID REFERENCES health_facilities(id) ON DELETE SET NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_district ON users(district_id);
CREATE INDEX IF NOT EXISTS idx_users_facility ON users(facility_id);

-- Augment inference_audit with the actor for accountability tracing.
ALTER TABLE inference_audit
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_inference_audit_user_id ON inference_audit(user_id);

-- Phase-4 cold archive.
CREATE TABLE IF NOT EXISTS inference_audit_archive (LIKE inference_audit INCLUDING ALL);
-- The primary key on inference_audit (id) propagates via LIKE INCLUDING ALL,
-- but the inherited FK on user_id is preserved by default. We append an
-- archive-specific timestamp + audit-row bell here.
CREATE INDEX IF NOT EXISTS idx_inference_audit_archive_generated
    ON inference_audit_archive(generated_at DESC);
