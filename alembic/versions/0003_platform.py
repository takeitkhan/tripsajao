"""super admin portal: platform tables, tenant status / limits / profile

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

from app.models.platform import PlatformAdmin, PlatformAudit, SupportSession

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # (on a fresh install 0001 already created all of this; every step below is safe to repeat)
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status varchar(16) NOT NULL DEFAULT 'ACTIVE'")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status_reason varchar(400)")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS limits_json jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS profile_json jsonb NOT NULL DEFAULT '{}'::jsonb")
    for t in (PlatformAdmin, PlatformAudit, SupportSession):
        t.__table__.create(bind, checkfirst=True)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        -- tenant-facing code must never be able to read or change platform data
        REVOKE ALL ON platform_admins, platform_audit, support_sessions FROM propsaas_app;
        -- a tenant session may edit its own settings and API keys, but never its status, limits or domain
        REVOKE UPDATE ON tenants FROM propsaas_app;
        GRANT UPDATE (name, api_key, api_secret_hash, api_scopes, settings_json) ON tenants TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE ON platform_admins, support_sessions TO propsaas_system;
        GRANT SELECT, INSERT ON platform_audit TO propsaas_system;               -- append-only
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support_sessions, platform_audit, platform_admins")
    for c in ("profile_json", "limits_json", "status_reason", "status"):
        op.execute(f"ALTER TABLE tenants DROP COLUMN IF EXISTS {c}")
