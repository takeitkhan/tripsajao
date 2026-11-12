"""Reseller channel: an agreement lets one business (the reseller) sell some properties of another (the owner).

These tables belong to two businesses at once, so they have no single `tenant_id`. Row level security shows a row to
either side (see migration 0004); the reseller can never write the owner's terms (policy WITH CHECK on the grants table)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, TZ, created_col, pk, tenant_fk, updated_col


class ChannelAgreement(Base):
    __tablename__ = "channel_agreements"
    __table_args__ = (
        UniqueConstraint("supplier_tenant_id", "reseller_tenant_id", name="uq_channel_agreements_pair"),
        CheckConstraint("supplier_tenant_id <> reseller_tenant_id", name="different_businesses"),
        CheckConstraint("status IN ('REQUESTED','INVITED','ACTIVE','PAUSED','DECLINED','ENDED')", name="status_valid"),
        CheckConstraint("commission_type IS NULL OR commission_type IN ('PERCENT','FLAT')", name="commission_type_valid"),
        CheckConstraint("commission_value IS NULL OR commission_value >= 0", name="commission_value_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    supplier_tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)   # the owner
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)     # snapshots, so each side can show the other's name
    reseller_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    initiated_by: Mapped[str] = mapped_column(String(8), nullable=False)        # OWNER | RESELLER
    commission_type: Mapped[Optional[str]] = mapped_column(String(8))           # per night: PERCENT of the night's price, or a FLAT amount
    commission_value: Mapped[Optional[Decimal]] = mapped_column(Money)
    settlement_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="MONTHLY", server_default=text("'MONTHLY'"))
    settlement_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default=text("10"))
    note: Mapped[Optional[str]] = mapped_column(String(500))
    ended_by: Mapped[Optional[str]] = mapped_column(String(8))
    decided_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class ChannelAgreementProperty(Base):
    """One property the owner lets the reseller sell. Commission may override the agreement's default."""
    __tablename__ = "channel_agreement_properties"
    __table_args__ = (
        UniqueConstraint("agreement_id", "property_id", name="uq_channel_agreement_properties_pair"),
        ForeignKeyConstraint(["supplier_tenant_id", "property_id"], ["properties.tenant_id", "properties.id"],
                             name="fk_channel_grant_property_same_tenant", ondelete="CASCADE"),
        CheckConstraint("(commission_type IS NULL) = (commission_value IS NULL)", name="override_complete"),
    )

    id: Mapped[uuid.UUID] = pk()
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    commission_type: Mapped[Optional[str]] = mapped_column(String(8))
    commission_value: Mapped[Optional[Decimal]] = mapped_column(Money)


class ChannelLedger(Base):
    """Append-only commission book between two businesses. Positive = the owner owes the reseller. Rows are never changed or deleted
    (the app database role has no UPDATE or DELETE on this table); a mistake is fixed by adding a reversing row."""
    __tablename__ = "channel_ledger"
    __table_args__ = (
        UniqueConstraint("booking_id", "entry_type", name="uq_channel_ledger_booking_type"),
        CheckConstraint("entry_type IN ('ACCRUAL','REVERSAL')", name="entry_type_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)              # accrual: the check-out day. reversal: the day it was cancelled
    # copied at the time, so a statement still reads well when the booking or property changes later
    booking_ref: Mapped[str] = mapped_column(String(16), nullable=False)
    property_name: Mapped[str] = mapped_column(String(200), nullable=False)
    guest_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = created_col()


class ChannelSettlement(Base):
    """A statement: the commission one owner must pay one reseller, with a due date, and both sides' confirmation."""
    __tablename__ = "channel_settlements"
    __table_args__ = (
        CheckConstraint("status IN ('DUE','PAID','CONFIRMED','DISPUTED')", name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = pk()
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reseller_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)               # MONTHLY | PER_BOOKING, as agreed when the statement was made
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="DUE", server_default=text("'DUE'"))
    paid_on: Mapped[Optional[date]] = mapped_column(Date)
    paid_reference: Mapped[Optional[str]] = mapped_column(String(120))
    paid_note: Mapped[Optional[str]] = mapped_column(String(500))
    paid_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    dispute_reason: Mapped[Optional[str]] = mapped_column(String(500))
    disputed_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()


class ChannelSettlementItem(Base):
    """Which ledger rows a statement covers. A ledger row can be in at most one statement."""
    __tablename__ = "channel_settlement_items"

    ledger_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_ledger.id", ondelete="CASCADE"), primary_key=True)
    settlement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel_settlements.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class ChannelCancellation(Base):
    """A reseller asks to cancel a confirmed booking it sold. It lives in the OWNER's business (so the owner's row level security applies);
    the reseller only reaches its own requests through `owner_scope`. The system works out the refund from the owner's rules; the owner decides."""
    __tablename__ = "channel_cancellations"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"], name="fk_channel_cancel_booking_same_tenant", ondelete="CASCADE"),
        CheckConstraint("status IN ('REQUESTED','CONFIRMED','DECLINED','WITHDRAWN')", name="status_valid"),
        Index("uq_channel_cancel_one_open", "booking_id", unique=True, postgresql_where=text("status = 'REQUESTED'")),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()                                   # the owner
    booking_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    booking_ref: Mapped[str] = mapped_column(String(16), nullable=False)
    agreement_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    reseller_tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    reseller_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="REQUESTED", server_default=text("'REQUESTED'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)          # what the guest had paid when the request was made
    days_before: Mapped[int] = mapped_column(Integer, nullable=False)            # days between the request and check-in
    policy_percent: Mapped[Decimal] = mapped_column(Money, nullable=False)       # the owner's rule that applied
    suggested_refund: Mapped[Decimal] = mapped_column(Money, nullable=False)
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Money)             # what the owner finally agreed to give back
    decision_note: Mapped[Optional[str]] = mapped_column(String(500))
    decided_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
