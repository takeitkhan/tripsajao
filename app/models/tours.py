import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, TZ, created_col, pk, tenant_fk, updated_col

_LIST = dict(nullable=False, default=list, server_default=text("'[]'::jsonb"))


class Package(Base):
    """A ready-made trip an agency keeps on file: itinerary, what is included, and a 'starting from' price."""
    __tablename__ = "packages"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_packages_tenant_slug"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(600))
    description: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    starting_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT", server_default=text("'BDT'"))
    itinerary: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)       # [{"day": 1, "title": "...", "details": "..."}]
    inclusions: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    exclusions: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    cover_image: Mapped[Optional[str]] = mapped_column(String(1000))
    pickup_location: Mapped[Optional[str]] = mapped_column(String(300))
    accommodation: Mapped[Optional[str]] = mapped_column(Text)
    trip_types: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)          # relax, trekking, ...
    bus_type: Mapped[Optional[str]] = mapped_column(String(80))
    other_transport: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)    # CNG, jeep, boat ...
    health_rules: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    essentials: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)         # what to bring
    photos: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class TourEvent(Base):
    """A dated departure the agency sells, usually made from a package (its details are copied, so later package edits do not rewrite history)."""
    __tablename__ = "tour_events"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_tour_events_tenant_slug"), Index("ix_tour_events_tenant_start", "tenant_id", "starts_on"))

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(600))
    description: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT", server_default=text("'BDT'"))
    seats: Mapped[Optional[int]] = mapped_column(Integer)
    itinerary: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    inclusions: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    exclusions: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    cover_image: Mapped[Optional[str]] = mapped_column(String(1000))
    pickup_location: Mapped[Optional[str]] = mapped_column(String(300))
    accommodation: Mapped[Optional[str]] = mapped_column(Text)
    trip_types: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)          # relax, trekking, ...
    bus_type: Mapped[Optional[str]] = mapped_column(String(80))
    other_transport: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)    # CNG, jeep, boat ...
    health_rules: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    essentials: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)         # what to bring
    photos: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    payment_methods: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))   # DRAFT | PUBLISHED | CLOSED
    published_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class Vendor(Base):
    """Someone the agency buys from: resort, restaurant, guide, chander gari, jeep, CNG, boat ..."""
    __tablename__ = "vendors"
    __table_args__ = (Index("ix_vendors_tenant_loc", "tenant_id", "location"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    category: Mapped[str] = mapped_column(String(14), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    address: Mapped[Optional[str]] = mapped_column(String(400))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class VendorRate(Base):
    """What a vendor charges for one thing (a double room per night, a guide per day, a jeep per trip)."""
    __tablename__ = "vendor_rates"

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    item: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(12), nullable=False, default="PER_UNIT", server_default=text("'PER_UNIT'"))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT", server_default=text("'BDT'"))
    notes: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class Budget(Base):
    """A saved cost estimate for a trip. Lines come from vendor rates (or are typed in); the totals are worked out on the server."""
    __tablename__ = "budgets"
    __table_args__ = (Index("ix_budgets_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    client_name: Mapped[Optional[str]] = mapped_column(String(200))
    client_phone: Mapped[Optional[str]] = mapped_column(String(60))
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tour_events.id", ondelete="SET NULL"))
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))
    people: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT", server_default=text("'BDT'"))
    lines: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    margin_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default=text("0"))
    cost_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))
    sell_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))   # DRAFT | SENT | WON | LOST
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class EventBooking(Base):
    """A seat booking on a published event, made through the API. Seats are held for a short time while the customer
    pays by hand (bKash, bank ...) and sends a screenshot; the business then checks the money and confirms."""
    __tablename__ = "event_bookings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "booking_ref", name="uq_event_bookings_tenant_ref"),
        Index("ix_event_bookings_event_status", "event_id", "status"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tour_events.id", ondelete="CASCADE"), nullable=False)
    booking_ref: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_info_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False, default=0)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=0, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT", server_default=text("'BDT'"))
    status: Mapped[str] = mapped_column(String(18), nullable=False, default="HOLD", server_default=text("'HOLD'"))   # HOLD | PAYMENT_SUBMITTED | CONFIRMED | CANCELLED | EXPIRED
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("partners.id", ondelete="SET NULL"))
    commission_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=0, server_default=text("0"))
    proofs_json: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)       # uploaded screenshots not yet attached to a payment
    payments_json: Mapped[list[Any]] = mapped_column(JSONB, **_LIST)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
