"""initial schema + row level security

Revision ID: 0001
Revises:
"""
from alembic import op

from app.models import Base, TENANT_TABLES

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")     # exclusion constraint on (unit_id, daterange)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")       # gen_random_uuid() on PG < 13
    Base.metadata.create_all(bind=bind)    # initial baseline only; use `alembic revision --autogenerate` afterwards

    # ---- Row Level Security: every tenant table isolated by app.tenant_id (set per transaction) ----
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = {TENANT_EXPR}) WITH CHECK (tenant_id = {TENANT_EXPR})")
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_self ON tenants USING (id = {TENANT_EXPR}) WITH CHECK (id = {TENANT_EXPR})")
    # NOTE: no FORCE RLS - the owner role (migrations, SECURITY DEFINER functions) bypasses; the app role cannot.

    # ---- SECURITY DEFINER lookups for the pre-authentication moment (no tenant known yet) ----
    for name, arg, col in (("app_tenant_by_api_key", "text", "api_key"), ("app_tenant_by_domain", "text", "domain"),
                           ("app_tenant_by_id", "uuid", "id")):
        op.execute(f"""
            CREATE FUNCTION {name}(p_value {arg}) RETURNS SETOF tenants
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
            AS $$ SELECT * FROM tenants WHERE {col} = p_value AND is_active $$""")
    op.execute("""
        CREATE FUNCTION app_resolve_vanity(p_code text)
        RETURNS TABLE (tenant_id uuid, partner_id uuid, domain text, settings_json jsonb)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$ SELECT p.tenant_id, p.id, t.domain, t.settings_json
              FROM partners p JOIN tenants t ON t.id = p.tenant_id
              WHERE p.vanity_code = p_code AND p.is_active AND t.is_active $$""")

    # ---- Grants: app role = DML only; system role (workers) = everything but it bypasses RLS ----
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT USAGE ON SCHEMA public TO propsaas_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO propsaas_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO propsaas_app;
        REVOKE INSERT, DELETE ON tenants FROM propsaas_app;                 -- tenants are provisioned out-of-band
        REVOKE UPDATE, DELETE ON partner_ledgers FROM propsaas_app;         -- ledger is append-only
        REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_tenant_by_api_key(text), app_tenant_by_domain(text),
              app_tenant_by_id(uuid), app_resolve_vanity(text) TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT USAGE ON SCHEMA public TO propsaas_system;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO propsaas_system;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    for fn in ("app_resolve_vanity(text)", "app_tenant_by_id(uuid)", "app_tenant_by_domain(text)", "app_tenant_by_api_key(text)"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    Base.metadata.drop_all(bind=op.get_bind())
