import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TZ, created_col, pk, tenant_fk, updated_col


class Customer(Base):
    """One person a business has dealt with: a guest who booked, someone who wrote through the website, or a hand-made entry.
    Identified by lower-case e-mail. Booking figures are never stored here; they are counted from the bookings."""
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_email"),
        Index("ix_customers_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)          # always lower-case
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="BOOKING", server_default=text("'BOOKING'"))   # BOOKING | CONTACT | MANUAL
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
