"""reseller channel: agreements between businesses, and the sale details on bookings

Revision ID: 0004
Revises: 0003
"""
from alembic import op

from app.models.channel import ChannelAgreement, ChannelAgreementProperty

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()
    # (a fresh install already got all of this from 0001; every step is safe to repeat)
    for col, typ in (("channel_tenant_id", "uuid"), ("channel_agreement_id", "uuid"), ("channel_name", "varchar(200)"),
                     ("channel_commission_type", "varchar(8)"), ("channel_commission_value", "numeric(12,2)"),
                     ("channel_commission_amount", "numeric(12,2) NOT NULL DEFAULT 0")):
        op.execute(f"ALTER TABLE bookings ADD COLUMN IF NOT EXISTS {col} {typ}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_channel_tenant_id ON bookings (channel_tenant_id)")
    for t in (ChannelAgreement, ChannelAgreementProperty):
        t.__table__.create(bind, checkfirst=True)

    # Each business sees only the agreements it is a side of. The reseller can never write the owner's grants.
    op.execute("ALTER TABLE channel_agreements ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS either_side ON channel_agreements")
    op.execute(f"CREATE POLICY either_side ON channel_agreements USING (supplier_tenant_id = {ME} OR reseller_tenant_id = {ME}) "
               f"WITH CHECK (supplier_tenant_id = {ME} OR reseller_tenant_id = {ME})")
    op.execute("ALTER TABLE channel_agreement_properties ENABLE ROW LEVEL SECURITY")
    for old in ("either_side", "either_side_read", "owner_writes"):
        op.execute(f"DROP POLICY IF EXISTS {old} ON channel_agreement_properties")
    op.execute(f"CREATE POLICY either_side_read ON channel_agreement_properties FOR SELECT USING (supplier_tenant_id = {ME} OR reseller_tenant_id = {ME})")
    op.execute(f"CREATE POLICY owner_writes ON channel_agreement_properties FOR ALL USING (supplier_tenant_id = {ME}) WITH CHECK (supplier_tenant_id = {ME})")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON channel_agreements, channel_agreement_properties TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE ON channel_agreements, channel_agreement_properties TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_agreement_properties, channel_agreements")
    for c in ("channel_commission_amount", "channel_commission_value", "channel_commission_type", "channel_name", "channel_agreement_id", "channel_tenant_id"):
        op.execute(f"ALTER TABLE bookings DROP COLUMN IF EXISTS {c}")
