"""Platform-level tables (the business that runs this SaaS). They have NO tenant_id and are not reachable by the
RLS-enforced app role: only the platform/system role reads and writes them."""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TZ, created_col, pk


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()


class PlatformAudit(Base):
    """Append-only trail of everything the super admins do."""
    __tablename__ = "platform_audit"
    __table_args__ = (Index("ix_platform_audit_created", "created_at"),)

    id: Mapped[uuid.UUID] = pk()
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    admin_email: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)        # no FK: the record must outlive the tenant
    tenant_name: Mapped[Optional[str]] = mapped_column(String(200))
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_col()


class SupportSession(Base):
    """A super admin signed in as a tenant's admin to help them."""
    __tablename__ = "support_sessions"
    __table_args__ = (Index("ix_support_sessions_started", "started_at"),)

    id: Mapped[uuid.UUID] = pk()
    admin_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    admin_email: Mapped[str] = mapped_column(String(320), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    tenant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    started_at: Mapped[datetime] = created_col()
    expires_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    ended_by: Mapped[Optional[str]] = mapped_column(String(20))              # admin | tenant | expired
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class ContactMessage(Base):
    """A message sent from the public website's contact form."""
    __tablename__ = "contact_messages"
    __table_args__ = (Index("ix_contact_messages_created", "created_at"),)

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    business_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other", server_default=text("'other'"))
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    lang: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default=text("'en'"))
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="NEW", server_default=text("'NEW'"))      # NEW | DONE
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_col()
