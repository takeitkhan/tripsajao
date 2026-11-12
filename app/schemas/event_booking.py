from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import ORMModel


class EventCustomer(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=40)
    address: Optional[str] = Field(default=None, max_length=300)
    emergency_contact: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=1000)
    guest_names: list[str] = Field(default_factory=list, max_length=50, description="Names of the other people travelling")


class EventHoldRequest(BaseModel):
    seats: int = Field(default=1, ge=1, le=50)
    customer: EventCustomer
    model_config = ConfigDict(json_schema_extra={"example": {"seats": 2, "customer": {
        "name": "Rafi Ahmed", "email": "rafi@example.com", "phone": "01711000000", "guest_names": ["Nadia Ahmed"]}}})


class EventPaymentIn(BaseModel):
    method: str = Field(min_length=2, max_length=60, description="For example bKash, Nagad, Bank transfer")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    trx_id: Optional[str] = Field(default=None, max_length=80, description="Transaction ID shown by the payment app")
    sender: Optional[str] = Field(default=None, max_length=80, description="Number or account the money was sent from")
    note: Optional[str] = Field(default=None, max_length=300)


class EventHoldOut(BaseModel):
    booking_ref: str
    token: str = Field(description="Secret for this booking. Shown ONCE; send it back on every later call.")
    status: str
    event_id: UUID
    seats: int
    unit_price: Decimal
    total_amount: Decimal
    currency: str
    hold_expires_at: datetime
    seconds_remaining: int
    payment_methods: list[str]
    partner_attributed: bool


class EventBookingPublic(BaseModel):
    booking_ref: str
    status: str
    event_id: UUID
    event_title: str
    seats: int
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    currency: str
    hold_expires_at: Optional[datetime]
    payment_methods: list[str]
    proofs: int = Field(description="Screenshots uploaded and waiting to be sent with a payment")
    payments: list[dict[str, Any]]


class PaymentDecision(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2, description="Amount actually received; defaults to what the customer reported")
    reason: Optional[str] = Field(default=None, max_length=300)


class EventBookingCancel(BaseModel):
    reason: str = Field(default="Cancelled by the business", min_length=1, max_length=300)


class EventBookingOut(ORMModel):
    id: UUID
    booking_ref: str
    event_id: UUID
    event_title: Optional[str] = None
    event_starts_on: Optional[date] = None
    customer_info_json: dict[str, Any]
    customer_id: Optional[UUID]
    seats: int
    unit_price: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    currency: str
    status: str
    hold_expires_at: Optional[datetime]
    partner_id: Optional[UUID]
    partner_name: Optional[str] = None
    commission_amount: Decimal
    proofs_json: list[Any]
    payments_json: list[Any]
    cancel_reason: Optional[str]
    created_at: datetime
