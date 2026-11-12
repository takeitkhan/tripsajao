"""media library (photos and videos)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

from app.models.media import MediaAsset

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("media_assets"):
        return          # fresh install: 0001 already created it (with RLS and grants)
    MediaAsset.__table__.create(bind)
    op.execute("ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON media_assets USING (tenant_id = {TENANT_EXPR}) WITH CHECK (tenant_id = {TENANT_EXPR})")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON media_assets TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE ON media_assets TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS media_assets")
