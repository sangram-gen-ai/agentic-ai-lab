-- Agentic AI Enterprise Lab — PostgreSQL bootstrap
-- Credentials must match .env (N8N_DB_* and POSTGRES_*)
-- Mounted as docker-entrypoint-initdb.d on first postgres boot

-- Dedicated n8n user — persists workflows, credentials, and executions
-- in the shared agentic_ai database (production pattern, not SQLite)
CREATE USER n8n_user WITH PASSWORD 'change_me_n8n';

\connect agentic_ai

-- Shared extensions for Spring Boot (Phase 2) and n8n
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- n8n creates and owns its tables in public schema:
--   workflow_entity, credentials_entity, execution_entity, execution_data, ...
GRANT USAGE, CREATE ON SCHEMA public TO n8n_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO n8n_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO n8n_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO n8n_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO n8n_user;
