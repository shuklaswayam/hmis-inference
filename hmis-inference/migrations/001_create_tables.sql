-- Migration 001: Create core tables for HMIS Inference System
-- Created: 2026-06-12

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table 1: districts
CREATE TABLE districts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    state VARCHAR(100) NOT NULL,
    population BIGINT,
    zone VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_districts_state ON districts(state);
CREATE INDEX idx_districts_zone ON districts(zone);

-- Table 2: health_facilities
CREATE TABLE health_facilities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    district_id UUID NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    facility_type VARCHAR(100) NOT NULL,
    beds_total INTEGER,
    icu_beds INTEGER,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_health_facilities_district_id ON health_facilities(district_id);
CREATE INDEX idx_health_facilities_type ON health_facilities(facility_type);
CREATE INDEX idx_health_facilities_location ON health_facilities(latitude, longitude);

-- Table 3: disease_reports (hypertable - composite PK with partitioning column)
CREATE TABLE disease_reports (
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    facility_id UUID NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
    disease_name TEXT NOT NULL,
    reported_date DATE NOT NULL,
    case_count INTEGER NOT NULL DEFAULT 0,
    deaths INTEGER NOT NULL DEFAULT 0,
    age_group TEXT,
    severity TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, reported_date)
);

CREATE INDEX idx_disease_reports_facility_id ON disease_reports(facility_id);
CREATE INDEX idx_disease_reports_disease_name ON disease_reports(disease_name);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('disease_reports', 'reported_date',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Table 4: facility_metrics (hypertable - composite PK with partitioning column)
CREATE TABLE facility_metrics (
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    facility_id UUID NOT NULL REFERENCES health_facilities(id) ON DELETE CASCADE,
    reported_date DATE NOT NULL,
    opd_visits INTEGER NOT NULL DEFAULT 0,
    icu_occupancy_pct DECIMAL(5,2),
    bed_occupancy_pct DECIMAL(5,2),
    emergency_visits INTEGER NOT NULL DEFAULT 0,
    maternal_deaths INTEGER NOT NULL DEFAULT 0,
    deliveries INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, reported_date)
);

CREATE INDEX idx_facility_metrics_facility_id ON facility_metrics(facility_id);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('facility_metrics', 'reported_date',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Table 5: inference_results
CREATE TABLE inference_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id UUID REFERENCES health_facilities(id) ON DELETE SET NULL,
    district_id UUID REFERENCES districts(id) ON DELETE SET NULL,
    inference_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    what_is_happening TEXT NOT NULL,
    why_it_happening TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence_score DECIMAL(3,2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    rule_flags JSONB,
    ml_scores JSONB,
    llm_generated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_inference_results_facility_id ON inference_results(facility_id);
CREATE INDEX idx_inference_results_district_id ON inference_results(district_id);
CREATE INDEX idx_inference_results_inference_type ON inference_results(inference_type);
CREATE INDEX idx_inference_results_severity ON inference_results(severity);
CREATE INDEX idx_inference_results_created_at ON inference_results(created_at);
CREATE INDEX idx_inference_results_expires_at ON inference_results(expires_at);

-- Table 6: policy_documents
CREATE TABLE policy_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    doc_type VARCHAR(100) NOT NULL,
    embedding VECTOR(1536),
    source_url VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_documents_doc_type ON policy_documents(doc_type);
CREATE INDEX idx_policy_documents_created_at ON policy_documents(created_at);

-- Vector similarity search index (requires pgvector)
CREATE INDEX idx_policy_documents_embedding ON policy_documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);