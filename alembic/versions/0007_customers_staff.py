"""customers (CRM) and per-user permissions

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.models.crm import Customer

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "permissions" not in cols:
        op.add_column("users", sa.Column("permissions", JSONB, nullable=True))
    Customer.__table__.create(bind, checkfirst=True)
    op.execute("ALTER TABLE customers ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON customers")
    op.execute(f"CREATE POLICY tenant_isolation ON customers USING (tenant_id = {ME}) WITH CHECK (tenant_id = {ME})")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON customers TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON customers TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customers")
    op.drop_column("users", "permissions")
