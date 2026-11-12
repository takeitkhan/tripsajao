"""packages, events, vendors, rates, budgets

Revision ID: 0008
Revises: 0007
"""
from alembic import op

from app.models.tours import Budget, Package, TourEvent, Vendor, VendorRate

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
TABLES = [Package, TourEvent, Vendor, VendorRate, Budget]


def upgrade() -> None:
    bind = op.get_bind()
    for m in TABLES:
        m.__table__.create(bind, checkfirst=True)
        t = m.__tablename__
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = {ME}) WITH CHECK (tenant_id = {ME})")
        op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO propsaas_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO propsaas_system;
          END IF;
        END $$;""")


def downgrade() -> None:
    for m in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {m.__tablename__}")
