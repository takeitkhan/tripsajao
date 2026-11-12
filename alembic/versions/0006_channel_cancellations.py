"""reseller cancellation requests and refunds

Revision ID: 0006
Revises: 0005
"""
from alembic import op

from app.models.channel import ChannelCancellation

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    ChannelCancellation.__table__.create(bind, checkfirst=True)
    op.execute("ALTER TABLE channel_cancellations ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON channel_cancellations")
    op.execute(f"CREATE POLICY tenant_isolation ON channel_cancellations USING (tenant_id = {ME}) WITH CHECK (tenant_id = {ME})")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON channel_cancellations TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON channel_cancellations TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_cancellations")
