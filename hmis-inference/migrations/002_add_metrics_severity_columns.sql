-- Migration 002: Add columns to facility_metrics so R008 (severe_stockout
-- → CRITICAL) and R009 (staff_attendance_dip → LOW) can fire.
-- Both columns are optional — back-compat with rows that pre-date the rules.
-- 2026-06-24.

ALTER TABLE facility_metrics
    ADD COLUMN IF NOT EXISTS medicine_days_remaining DOUBLE PRECISION
        CHECK (medicine_days_remaining IS NULL OR medicine_days_remaining >= 0),
    ADD COLUMN IF NOT EXISTS staff_attendance_pct DOUBLE PRECISION
        CHECK (staff_attendance_pct IS NULL
               OR (staff_attendance_pct >= 0 AND staff_attendance_pct <= 100));
