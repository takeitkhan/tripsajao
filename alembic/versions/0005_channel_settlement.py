"""reseller commission book, statements and settlement

Revision ID: 0005
Revises: 0004
"""
from alembic import op

from app.models.channel import ChannelLedger, ChannelSettlement, ChannelSettlementItem

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ME = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
BOTH = f"(supplier_tenant_id = {ME} OR reseller_tenant_id = {ME})"


def upgrade() -> None:
    bind = op.get_bind()
    for t in (ChannelLedger, ChannelSettlement, ChannelSettlementItem):
        t.__table__.create(bind, checkfirst=True)
    for table in ("channel_ledger", "channel_settlements", "channel_settlement_items"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        for old in ("either_side_read", "owner_writes", "either_side_update"):
            op.execute(f"DROP POLICY IF EXISTS {old} ON {table}")
        op.execute(f"CREATE POLICY either_side_read ON {table} FOR SELECT USING {BOTH}")
        op.execute(f"CREATE POLICY owner_writes ON {table} FOR INSERT WITH CHECK (supplier_tenant_id = {ME})")
    op.execute(f"CREATE POLICY either_side_update ON channel_settlements FOR UPDATE USING {BOTH} WITH CHECK {BOTH}")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        GRANT SELECT, INSERT ON channel_ledger, channel_settlement_items TO propsaas_app;
        GRANT SELECT, INSERT, UPDATE ON channel_settlements TO propsaas_app;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT ON channel_ledger, channel_settlement_items TO propsaas_system;
        GRANT SELECT, INSERT, UPDATE ON channel_settlements TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_settlement_items, channel_settlements, channel_ledger")
