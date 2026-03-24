-- LinX (灵枢) - Database Initialization Script
-- This script runs automatically when PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- For JSONB indexing

-- Create database if it doesn't exist (handled by POSTGRES_DB env var)
-- This script runs after database creation

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'LinX (灵枢) database initialized successfully';
END $$;
