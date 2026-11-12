import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TZ, created_col, enum_col, pk, tenant_fk, updated_col
from app.models.enums import Role


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    api_secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    api_scopes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # deposit_percent, hold_seconds, min_payout, timezone, attribution_model, company{}, path templates ...
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # ACTIVE | PENDING (waiting for the super admin) | SUSPENDED | REJECTED. is_active is kept equal to (status == ACTIVE).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))
    status_reason: Mapped[Optional[str]] = mapped_column(String(400))
    # {"max_properties": 5, "max_units": 40, "max_partners": 20, "media_quota_mb": 2000}; a missing key means "no limit" (media: platform default)
    limits_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    # who registered: owner name, phone, country, business type, how they joined
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_col()

    users: Mapped[list["User"]] = relationship(viewonly=True, lazy="raise")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = enum_col(Role, default=Role.STAFF)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # None = the role's standard access. A list = exactly these scopes (MANAGER / STAFF only; ADMIN always has everything).
    permissions: Mapped[Optional[list[Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_col()
