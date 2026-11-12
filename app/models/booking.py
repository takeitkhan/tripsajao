import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, TZ, created_col, enum_col, pk, tenant_fk, updated_col
from app.models.enums import BookingStatus


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bookings_tenant_id_id"),
        UniqueConstraint("tenant_id", "booking_ref", name="uq_bookings_tenant_ref"),
        ForeignKeyConstraint(["tenant_id", "unit_id"], ["units.tenant_id", "units.id"], name="fk_bookings_unit_same_tenant"),
        ForeignKeyConstraint(["tenant_id", "property_id"], ["properties.tenant_id", "properties.id"],
                             name="fk_bookings_property_same_tenant"),
        # partner_id is nullable: MATCH SIMPLE skips the check when NULL
        ForeignKeyConstraint(["tenant_id", "partner_id"], ["partners.tenant_id", "partners.id"],
                             name="fk_bookings_partner_same_tenant"),
        CheckConstraint("check_out > check_in", name="dates_valid"),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= total_amount", name="paid_within_total"),
        # Overbooking guard of last resort (needs btree_gist): no two live bookings of the same unit may overlap.
        ExcludeConstraint(
            ("unit_id", "="),
            (text("daterange(check_in, check_out, '[)')"), "&&"),
            using="gist",
            where=text("status IN ('HOLD','CONFIRMED')"),
            name="ex_bookings_no_overlap",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    booking_ref: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)   # denormalised: locking + dashboards
    partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)           # auto-attributed via cookie
    customer_info_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    commission_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))  # snapshot at hold time
    # Sold by another business (a reseller) under an agreement. The terms are copied here at hold time, so later changes never touch this booking.
    channel_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)
    channel_agreement_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    channel_name: Mapped[Optional[str]] = mapped_column(String(200))
    channel_commission_type: Mapped[Optional[str]] = mapped_column(String(8))
    channel_commission_value: Mapped[Optional[Decimal]] = mapped_column(Money)
    channel_commission_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"), server_default=text("0"))
    status: Mapped[BookingStatus] = enum_col(BookingStatus, default=BookingStatus.HOLD)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(TZ, index=True)
    price_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    payments_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()

    unit = relationship("Unit", viewonly=True, lazy="raise")
    partner = relationship("Partner", viewonly=True, lazy="raise")
