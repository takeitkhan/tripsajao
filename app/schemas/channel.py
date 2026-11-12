from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.booking import ConfirmRequest, HoldRequest

CommissionType = Literal["PERCENT", "FLAT"]
Money = Field(ge=0, max_digits=12, decimal_places=2)


def _check_commission(kind: str | None, value: Decimal | None) -> None:
    if kind == "PERCENT" and value is not None and value > 100:
        raise ValueError("A percentage commission cannot be more than 100")


class PropertyGrant(BaseModel):
    """A property the reseller may sell. Leave the commission empty to use the agreement's default."""
    property_id: UUID
    commission_type: CommissionType | None = None
    commission_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def _both_or_none(self):
        if (self.commission_type is None) != (self.commission_value is None):
            raise ValueError("Give both the commission type and value for a property, or neither")
        _check_commission(self.commission_type, self.commission_value)
        return self


class Terms(BaseModel):
    """What the owner allows: default commission per night, and which properties."""
    commission_type: CommissionType
    commission_value: Decimal = Field(ge=0, max_digits=12, decimal_places=2, description="Per night: a percent of the night's price, or a flat amount")
    properties: list[PropertyGrant] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    settlement_mode: Literal["MONTHLY", "PER_BOOKING"] | None = Field(default=None, description="MONTHLY: pay by a day of the month. PER_BOOKING: pay each booking within some days of check-out. Empty keeps the current choice.")
    settlement_day: int | None = Field(default=None, ge=1, le=60, description="MONTHLY: day of the month (1 to 28). PER_BOOKING: days after check-out (1 to 60)")

    @model_validator(mode="after")
    def _terms(self):
        _check_commission(self.commission_type, self.commission_value)
        if self.settlement_mode == "MONTHLY" and self.settlement_day is not None and self.settlement_day > 28:
            raise ValueError("For monthly settlement choose a day from 1 to 28")
        ids = [g.property_id for g in self.properties]
        if len(ids) != len(set(ids)):
            raise ValueError("A property is listed twice")
        return self


class RequestAccess(BaseModel):
    owner_domain: str = Field(min_length=3, max_length=253, description="The sign-in domain of the business whose rooms you want to sell")
    note: str | None = Field(default=None, max_length=500)


class Invite(Terms):
    reseller_domain: str = Field(min_length=3, max_length=253)


class AgreementProperty(BaseModel):
    property_id: UUID
    name: str | None
    commission_type: str
    commission_value: Decimal
    is_default: bool


class AgreementOut(BaseModel):
    id: UUID
    role: Literal["OWNER", "RESELLER"]
    counterpart: str
    status: str
    initiated_by: str
    awaiting: Literal["YOU", "THEM"] | None
    commission_type: str | None
    commission_value: Decimal | None
    settlement_mode: str
    settlement_day: int
    note: str | None
    properties: list[AgreementProperty]
    created_at: datetime
    updated_at: datetime


class ChannelProperty(BaseModel):
    agreement_id: UUID
    owner: str
    property_id: UUID
    name: str
    type: str
    location: str | None
    description: str | None
    amenities: list[Any]
    media: list[Any]
    commission_type: str
    commission_value: Decimal


class ChannelUnit(BaseModel):
    unit_id: UUID
    unit_name: str
    unit_type: str
    capacity: int
    facilities: list[Any]
    currency: str
    total: Decimal
    nights: int
    your_commission: Decimal


class ChannelHold(HoldRequest):
    agreement_id: UUID
    property_id: UUID


class ChannelConfirm(ConfirmRequest):
    agreement_id: UUID


class ChannelBookingOut(BaseModel):
    id: UUID
    booking_ref: str
    agreement_id: UUID | None
    owner: str
    property: str
    unit: str
    customer: dict[str, Any]
    check_in: date
    check_out: date
    nights: int
    guests: int
    currency: str
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    your_commission: Decimal
    commission_type: str | None
    commission_value: Decimal | None
    status: str
    hold_expires_at: datetime | None
    cancel_reason: str | None
    cancellation: dict[str, Any] | None = None     # open or latest cancellation request: id, status, suggested_refund, refund_amount
    created_at: datetime


class ChannelBookingPage(BaseModel):
    items: list[ChannelBookingOut]
    total: int
    limit: int
    offset: int
    unavailable: list[str] = []


# ------------------------------------------------------------------------------------------ commissions and statements
class StatementLine(BaseModel):
    booking_ref: str
    property_name: str
    guest_name: str
    check_in: date
    check_out: date
    kind: Literal["COMMISSION", "REFUND_OF_COMMISSION"]
    amount: Decimal


class StatementOut(BaseModel):
    id: UUID
    code: str
    agreement_id: UUID
    role: Literal["OWNER", "RESELLER"]
    counterpart: str
    mode: str
    period_start: date
    period_end: date
    amount: Decimal
    currency: str
    due_date: date
    status: Literal["DUE", "PAID", "CONFIRMED", "DISPUTED"]
    overdue: bool
    days_overdue: int
    paid_on: date | None = None
    paid_reference: str | None = None
    paid_note: str | None = None
    paid_at: datetime | None = None
    confirmed_at: datetime | None = None
    dispute_reason: str | None = None
    disputed_at: datetime | None = None
    created_at: datetime
    lines: list[StatementLine] | None = None


class MarkPaid(BaseModel):
    reference: str = Field(min_length=3, max_length=120, description="Bank, bKash or cheque reference")
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class Dispute(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MoneyRow(BaseModel):
    currency: str
    upcoming: Decimal            # sold, guest has not checked out yet
    unbilled: Decimal            # earned, not on a statement yet
    to_pay: Decimal              # on statements waiting for payment (or disputed)
    awaiting_confirmation: Decimal   # marked paid, the reseller has not confirmed yet
    settled: Decimal             # confirmed received
    overdue: Decimal


class SummaryOut(BaseModel):
    as_owner: list[MoneyRow]     # commission I owe to resellers
    as_reseller: list[MoneyRow]  # commission owed to me


# ------------------------------------------------------------------------------------------ cancellation and refund
class RefundRule(BaseModel):
    days_before: int = Field(ge=0, le=365, description="At least this many days before check-in ...")
    refund_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2, description="... this percent of what the guest paid is refunded")


class CancellationPolicy(BaseModel):
    rules: list[RefundRule] = Field(min_length=1, max_length=10)
    is_default: bool = False

    @model_validator(mode="after")
    def _unique(self):
        days = [r.days_before for r in self.rules]
        if len(days) != len(set(days)):
            raise ValueError("Two rules have the same number of days")
        return self


class CancelQuote(BaseModel):
    booking_id: UUID
    booking_ref: str
    status: str
    check_in: date
    currency: str
    paid_amount: Decimal
    days_before: int
    refund_percent: Decimal
    refund_amount: Decimal
    rule_text: str
    can_request: bool
    why_not: str | None = None


class CancelRequest(BaseModel):
    agreement_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class CancelDecision(BaseModel):
    refund_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2, description="Leave empty to give the suggested refund")
    note: str | None = Field(default=None, max_length=500)


class CancelDecline(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class CancellationOut(BaseModel):
    id: UUID
    booking_id: UUID
    booking_ref: str
    agreement_id: UUID
    role: Literal["OWNER", "RESELLER"]
    counterpart: str
    property: str
    guest: str
    check_in: date
    check_out: date
    currency: str
    total_amount: Decimal
    paid_amount: Decimal
    days_before: int
    refund_percent: Decimal
    suggested_refund: Decimal
    refund_amount: Decimal | None
    status: Literal["REQUESTED", "CONFIRMED", "DECLINED", "WITHDRAWN"]
    reason: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None
