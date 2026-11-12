-- Runs once on first container start (as the bootstrap superuser).
CREATE ROLE propsaas_app    LOGIN PASSWORD 'app_pw'    NOSUPERUSER NOBYPASSRLS;
CREATE ROLE propsaas_system LOGIN PASSWORD 'system_pw' NOSUPERUSER BYPASSRLS;
