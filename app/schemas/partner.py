from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import CommissionType, LedgerType, PartnerType, PayoutStatus
from app.schemas.common import ORMModel

_VANITY = r"^[A-Za-z0-9_-]{4,32}$"


class PartnerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    partner_type: PartnerType
    commission_type: CommissionType
    commission_value: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    vanity_code: str | None = Field(default=None, pattern=_VANITY, description="Auto-generated when omitted")

    @model_validator(mode="after")
    def _pct(self):
        if self.commission_type == CommissionType.PERCENT and self.commission_value > 100:
            raise ValueError("percent commission cannot exceed 100")
        return self

    model_config = ConfigDict(json_schema_extra={"example": {
        "name": "Sunrise Travels", "email": "ops@sunrise.example", "password": "Str0ng-Passw0rd!",
        "partner_type": "B2B", "commission_type": "PERCENT", "commission_value": "10.00"}})


class PartnerUpdate(BaseModel):
    name: str | None = None
    commission_type: CommissionType | None = None
    commission_value: Decimal | None = Field(default=None, ge=0)
    vanity_code: str | None = Field(default=None, pattern=_VANITY)
    is_active: bool | None = None


class PartnerOut(ORMModel):
    id: UUID
    name: str
    email: EmailStr
    partner_type: PartnerType
    commission_type: CommissionType
    commission_value: Decimal
    vanity_code: str
    is_active: bool
    short_link: str | None = None


class LedgerEntryOut(ORMModel):
    id: UUID
    booking_id: UUID | None
    payout_id: UUID | None
    credit: Decimal
    debit: Decimal
    balance: Decimal
    transaction_type: LedgerType
    note: str | None
    created_at: datetime


class LedgerStatement(BaseModel):
    partner_id: UUID
    total_credit: Decimal
    total_debit: Decimal
    closing_balance: Decimal
    reserved_for_payouts: Decimal
    available_for_payout: Decimal
    entries: list[LedgerEntryOut]


class PartnerDashboard(BaseModel):
    confirmed_bookings: int
    gross_sales: Decimal
    commission_earned: Decimal
    paid_out: Decimal
    ledger_balance: Decimal
    reserved_for_payouts: Decimal
    available_for_payout: Decimal
    min_payout: Decimal
    short_link: str


class PartnerBookingOut(ORMModel):
    booking_ref: str
    check_in: Any
    check_out: Any
    total_amount: Decimal
    paid_amount: Decimal
    commission_amount: Decimal
    status: str


class PayoutDetails(BaseModel):
    method: Literal["BANK", "MOBILE_WALLET", "MANUAL"]
    account_name: str = Field(min_length=1, max_length=200)
    account_number: str = Field(min_length=3, max_length=60)
    bank_name: str | None = None
    routing_code: str | None = None
    note: str | None = Field(default=None, max_length=300)


class PayoutCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payout_details: PayoutDetails
    model_config = ConfigDict(json_schema_extra={"example": {
        "amount": "5000.00", "payout_details": {
            "method": "BANK", "account_name": "Sunrise Travels Ltd", "account_number": "1234567890", "bank_name": "Example Bank"}}})


class PayoutReview(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class PayoutOut(ORMModel):
    id: UUID
    partner_id: UUID
    amount: Decimal
    status: PayoutStatus
    payout_details: dict[str, Any] = Field(validation_alias="payout_details_json")
    review_note: str | None
    created_at: datetime
    paid_at: datetime | None
