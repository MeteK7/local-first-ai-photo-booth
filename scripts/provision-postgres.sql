\set ON_ERROR_STOP on

-- Run once, while connected to the maintenance database as a local administrator.
-- Abort before changing anything if a proposed role or database name is in use.
DO $$
BEGIN
    IF current_database() <> 'postgres' THEN
        RAISE EXCEPTION 'Connect to the postgres maintenance database.';
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'photobooth_app')
       OR EXISTS (SELECT FROM pg_database WHERE datname IN ('photobooth_dev', 'photobooth_test')) THEN
        RAISE EXCEPTION 'A photo booth database or role already exists. Check ownership before proceeding.';
    END IF;
END
$$;

BEGIN;
CREATE ROLE photobooth_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SET LOCAL password_encryption = 'scram-sha-256';
\password photobooth_app
COMMIT;

CREATE DATABASE photobooth_dev OWNER photobooth_app;
REVOKE CONNECT ON DATABASE photobooth_dev FROM PUBLIC;
CREATE DATABASE photobooth_test OWNER photobooth_app;
REVOKE CONNECT ON DATABASE photobooth_test FROM PUBLIC;
