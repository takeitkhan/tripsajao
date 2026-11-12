from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import BookingStatus
from app.schemas.common import ORMModel


class CustomerInfo(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class HoldRequest(BaseModel):
    unit_id: UUID
    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1, le=100)
    customer: CustomerInfo

    @model_validator(mode="after")
    def _dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if (self.check_out - self.check_in).days > 60:
            raise ValueError("maximum stay is 60 nights")
        return self

    model_config = ConfigDict(json_schema_extra={"example": {
        "unit_id": "00000000-0000-0000-0000-000000000000", "check_in": "2026-12-24", "check_out": "2026-12-27", "guests": 2,
        "customer": {"name": "Rahim Uddin", "email": "rahim@example.com", "phone": "+8801700000000"}}})


class HoldOut(BaseModel):
    booking_id: UUID
    booking_ref: str
    status: BookingStatus
    unit_id: UUID
    check_in: date
    check_out: date
    nights: int
    currency: str
    total_amount: Decimal
    deposit_amount: Decimal
    hold_expires_at: datetime
    seconds_remaining: int
    price_breakdown: dict[str, Any]
    partner_attributed: bool


class ConfirmRequest(BaseModel):
    booking_id: UUID
    payment_mode: Literal["FULL", "PARTIAL"] = "FULL"
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_reference: str = Field(min_length=3, max_length=100, description="Gateway transaction id (idempotency key)")
    gateway: str = Field(default="manual", max_length=40)
    model_config = ConfigDict(json_schema_extra={"example": {
        "booking_id": "00000000-0000-0000-0000-000000000000", "payment_mode": "PARTIAL",
        "amount": "6750.00", "payment_reference": "TXN-84721", "gateway": "stripe"}})


class ConfirmOut(BaseModel):
    booking_id: UUID
    booking_ref: str
    status: BookingStatus
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    payment_state: Literal["PARTIAL", "PAID"]


class CancelRequest(BaseModel):
    reason: str = Field(default="CANCELLED_BY_STAFF", max_length=100)


class BookingOut(ORMModel):
    id: UUID
    booking_ref: str
    unit_id: UUID
    property_id: UUID
    partner_id: UUID | None
    customer: dict[str, Any] = Field(validation_alias="customer_info_json")
    check_in: date
    check_out: date
    guests: int
    currency: str
    total_amount: Decimal
    paid_amount: Decimal
    commission_amount: Decimal
    channel_name: str | None = None
    channel_commission_amount: Decimal = Decimal("0")
    status: BookingStatus
    hold_expires_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    payments: list[Any] = Field(default=[], validation_alias="payments_json")
    price_breakdown: dict[str, Any] = Field(default={}, validation_alias="price_breakdown_json")


class AvailableUnit(BaseModel):
    unit_id: UUID
    unit_name: str
    unit_type: str
    capacity: int
    facilities: list[Any]
    currency: str
    total: Decimal
