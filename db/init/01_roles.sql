-- Creates the restricted application role and grants minimum required privileges.
-- Executed by the postgres:16 image at first-run (docker-entrypoint-initdb.d).
-- Requires: APP_DB_PASSWORD and POSTGRES_DB env vars set on the container.

\getenv app_db_password APP_DB_PASSWORD
\getenv postgres_db POSTGRES_DB

CREATE ROLE tenant_app_user WITH
    LOGIN
    PASSWORD :'app_db_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;

-- Database-level access
GRANT CONNECT ON DATABASE :"postgres_db" TO tenant_app_user;

-- Schema-level access (CREATE needed so Alembic can run migrations in dev)
GRANT USAGE  ON SCHEMA public TO tenant_app_user;
GRANT CREATE ON SCHEMA public TO tenant_app_user;

-- Default privileges for any tables/sequences the superuser might create later
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tenant_app_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO tenant_app_user;
