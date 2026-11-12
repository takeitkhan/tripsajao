import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

BUSINESS_TYPES = ["Travel agency", "Tour operator", "Resort", "Hotel", "Houseboat", "Other"]
MFS_PROVIDERS = ["bKash", "Nagad", "Rocket", "Upay", "Other"]
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /._-]{3,39}$")


def _clean(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return v or None


class BankAccount(BaseModel):
    bank_name: str = Field(min_length=2, max_length=120)
    branch: Optional[str] = Field(default=None, max_length=120)
    account_name: str = Field(min_length=2, max_length=160)
    account_number: str = Field(min_length=4, max_length=40, pattern=r"^[0-9A-Za-z -]+$")
    routing_no: Optional[str] = Field(default=None, max_length=20)
    swift: Optional[str] = Field(default=None, max_length=20)
    is_primary: bool = False
    show_to_customers: bool = Field(default=True, description="Websites may show this account to customers who pay by hand")


class MfsAccount(BaseModel):
    provider: str = Field(min_length=2, max_length=40, description="bKash, Nagad, Rocket, Upay or another")
    account_type: Literal["Personal", "Agent", "Merchant"] = "Personal"
    number: str = Field(min_length=6, max_length=20, pattern=r"^\+?[0-9 -]+$")
    account_name: Optional[str] = Field(default=None, max_length=160)
    is_primary: bool = False
    show_to_customers: bool = True


class BusinessIn(BaseModel):
    name: str = Field(min_length=2, max_length=200, description="The name shown in the header and on your website")
    legal_name: Optional[str] = Field(default=None, max_length=200)
    business_type: Optional[str] = Field(default=None, max_length=40)
    established_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    logo_url: Optional[str] = Field(default=None, max_length=1000, description="REQUIRED")
    owner_name: Optional[str] = Field(default=None, max_length=200)
    owner_photo: Optional[str] = Field(default=None, max_length=1000, description="REQUIRED")
    owner_phone: Optional[str] = Field(default=None, max_length=40)
    owner_email: Optional[str] = Field(default=None, max_length=320)
    license_no: Optional[str] = Field(default=None, max_length=60, description="Trade or tourism licence number")
    license_expiry: Optional[date] = None
    tin: Optional[str] = Field(default=None, max_length=40, description="Optional")
    bin: Optional[str] = Field(default=None, max_length=40, description="Optional")
    other_registration: Optional[str] = Field(default=None, max_length=120)
    whatsapp: Optional[str] = Field(default=None, max_length=40)
    website: Optional[str] = Field(default=None, max_length=300)
    office_hours: Optional[str] = Field(default=None, max_length=200)
    bank_accounts: list[BankAccount] = Field(default_factory=list, max_length=10)
    mfs_accounts: list[MfsAccount] = Field(default_factory=list, max_length=10)
    hold_minutes: int = Field(default=10, ge=1, le=120, description="How long room seats are kept while a customer pays")
    event_hold_minutes: int = Field(default=10, ge=1, le=120, description="How long event seats are kept while a customer pays")
    deposit_percent: int = Field(default=50, ge=1, le=100, description="Minimum advance for a part payment")
    terms: Optional[str] = Field(default=None, max_length=4000)
    cancellation_policy: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("name", "legal_name", "business_type", "logo_url", "owner_name", "owner_photo", "owner_phone", "owner_email", "license_no", "tin", "bin",
                     "other_registration", "whatsapp", "website", "office_hours", "terms", "cancellation_policy", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("tin", "bin")
    @classmethod
    def _id(cls, v):
        v = _clean(v)
        if v and not _ID.match(v):
            raise ValueError("Use letters, digits and dashes only (4 to 40 characters)")
        return v

    @model_validator(mode="after")
    def _one_primary(self):
        for items, what in ((self.bank_accounts, "bank account"), (self.mfs_accounts, "mobile banking account")):
            if sum(1 for a in items if a.is_primary) > 1:
                raise ValueError(f"Only one {what} can be the main one")
        return self


class BusinessOut(BusinessIn):
    missing: list[str] = Field(default_factory=list, description="Required items still empty")
    complete: bool = True


REQUIRED = {"logo_url": "Business logo", "owner_photo": "Owner's photo"}


class PublicAccount(BaseModel):
    kind: Literal["BANK", "MFS"]
    title: str
    account_name: Optional[str] = None
    number: str
    detail: Optional[str] = None
    is_primary: bool = False


class BusinessPublic(BaseModel):
    name: str
    legal_name: Optional[str] = None
    logo_url: Optional[str] = None
    tagline: Optional[str] = None
    owner_name: Optional[str] = None
    owner_photo: Optional[str] = None
    license_no: Optional[str] = None
    tin: Optional[str] = None
    bin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    office_hours: Optional[str] = None
    currency: Optional[str] = None
    terms: Optional[str] = None
    cancellation_policy: Optional[str] = None
    payment_accounts: list[PublicAccount] = Field(default_factory=list, description="Where customers can send money by hand")
