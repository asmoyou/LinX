-- Digital Workforce Platform - Database Initialization Script
-- This script runs automatically when PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- For JSONB indexing

-- Create database if it doesn't exist (handled by POSTGRES_DB env var)
-- This script runs after database creation

-- Set timezone
SET timezone = 'UTC';

-- Create initial schema version table
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Insert initial version
INSERT INTO schema_version (version, description) 
VALUES (0, 'Initial database setup')
ON CONFLICT (version) DO NOTHING;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Digital Workforce Platform database initialized successfully';
END $$;
