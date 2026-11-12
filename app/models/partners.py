import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKeyConstraint, Identity, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, TZ, created_col, enum_col, pk, tenant_fk, updated_col
from app.models.enums import CommissionType, LedgerType, PartnerType, PayoutStatus


class Partner(Base):
    __tablename__ = "partners"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_partners_tenant_id_id"),
        UniqueConstraint("tenant_id", "email", name="uq_partners_tenant_email"),
        UniqueConstraint("vanity_code", name="uq_partners_vanity_code"),   # globally unique -> /go/<code>
        CheckConstraint("commission_value >= 0", name="commission_non_negative"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)   # added: partner portal login
    partner_type: Mapped[PartnerType] = enum_col(PartnerType)
    commission_type: Mapped[CommissionType] = enum_col(CommissionType)
    commission_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    vanity_code: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = created_col()

    ledger_entries: Mapped[list["PartnerLedger"]] = relationship(back_populates="partner", viewonly=True, lazy="raise")
    payouts: Mapped[list["PayoutRequest"]] = relationship(back_populates="partner", viewonly=True, lazy="raise")


class PartnerLedger(Base):
    """Append-only. The app role has no UPDATE/DELETE privilege on this table (see migration)."""
    __tablename__ = "partner_ledgers"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "partner_id"], ["partners.tenant_id", "partners.id"],
                             name="fk_ledger_partner_same_tenant"),
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"],
                             name="fk_ledger_booking_same_tenant"),
        ForeignKeyConstraint(["tenant_id", "payout_id"], ["payout_requests.tenant_id", "payout_requests.id"],
                             name="fk_ledger_payout_same_tenant"),
        CheckConstraint("credit >= 0 AND debit >= 0", name="amounts_non_negative"),
    )

    id: Mapped[uuid.UUID] = pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, nullable=False)   # strict ordering
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    partner_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    booking_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)
    payout_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    event_booking_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)   # set instead of booking_id for an event seat sale
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    balance: Mapped[Decimal] = mapped_column(Money, nullable=False)     # running balance after this row
    transaction_type: Mapped[LedgerType] = enum_col(LedgerType)
    note: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_col()

    partner: Mapped["Partner"] = relationship(back_populates="ledger_entries", viewonly=True, lazy="raise")


class PayoutRequest(Base):
    __tablename__ = "payout_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_payout_requests_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "partner_id"], ["partners.tenant_id", "partners.id"],
                             name="fk_payout_partner_same_tenant"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    partner_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[PayoutStatus] = enum_col(PayoutStatus, default=PayoutStatus.PENDING)
    payout_details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column()
    review_note: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
    paid_at: Mapped[Optional[datetime]] = mapped_column(TZ)

    partner: Mapped["Partner"] = relationship(back_populates="payouts", viewonly=True, lazy="raise")
