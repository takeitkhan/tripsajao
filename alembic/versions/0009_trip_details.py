"""package and event: pickup, accommodation, trip types, transport, health rules, warnings, essentials, photos, payment methods

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

LISTS = ["trip_types", "other_transport", "health_rules", "warnings", "essentials", "photos"]


def _add(table: str, extra_lists: list[str]) -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    for name, col in [("pickup_location", sa.String(300)), ("accommodation", sa.Text()), ("bus_type", sa.String(80))]:
        if name not in have:
            op.add_column(table, sa.Column(name, col, nullable=True))
    for name in LISTS + extra_lists:
        if name not in have:
            op.add_column(table, sa.Column(name, JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))


def upgrade() -> None:
    _add("packages", [])
    _add("tour_events", ["payment_methods"])


def downgrade() -> None:
    for t, extra in (("packages", []), ("tour_events", ["payment_methods"])):
        for name in ["pickup_location", "accommodation", "bus_type"] + LISTS + extra:
            op.drop_column(t, name)
