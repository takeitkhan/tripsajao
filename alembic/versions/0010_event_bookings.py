"""event bookings (+ ledger link)

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

from app.models.tours import EventBooking

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    EventBooking.__table__.create(bind, checkfirst=True)
    t = "event_bookings"
    op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
    op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = {ME}) WITH CHECK (tenant_id = {ME})")
    op.execute(f"""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO propsaas_app; END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO propsaas_system; END IF;
    END $$;""")
    cols = {c["name"] for c in sa.inspect(bind).get_columns("partner_ledgers")}
    if "event_booking_id" not in cols:
        op.add_column("partner_ledgers", sa.Column("event_booking_id", sa.Uuid(), nullable=True))
        op.create_index("ix_partner_ledgers_event_booking_id", "partner_ledgers", ["event_booking_id"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_bookings")
