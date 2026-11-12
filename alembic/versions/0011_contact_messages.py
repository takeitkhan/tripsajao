"""public website contact messages

Revision ID: 0011
Revises: 0010
"""
from alembic import op

from app.models.platform import ContactMessage

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ContactMessage.__table__.create(op.get_bind(), checkfirst=True)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_app') THEN
        REVOKE ALL ON contact_messages FROM propsaas_app;        -- tenant code never touches platform data
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propsaas_system') THEN
        GRANT SELECT, INSERT, UPDATE ON contact_messages TO propsaas_system;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_messages")
