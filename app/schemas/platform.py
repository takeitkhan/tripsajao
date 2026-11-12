import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,251}[a-z0-9])$")


def clean_domain(v: str) -> str:
    v = v.strip().lower()
    if not DOMAIN_RE.match(v) or ".." in v or v.startswith(("-", ".")):
        raise ValueError("Use only lowercase letters, numbers, dots and hyphens (3 to 253 characters), e.g. lakeview-resort.com")
    return v


class PAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str


class PLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PRefresh(BaseModel):
    refresh_token: str


class PTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    admin: PAdmin


class Limits(BaseModel):
    """Leave a field empty for "no limit" (storage: the platform default)."""
    model_config = ConfigDict(extra="forbid")
    max_properties: int | None = Field(default=None, ge=0, le=100000)
    max_units: int | None = Field(default=None, ge=0, le=1000000)
    max_partners: int | None = Field(default=None, ge=0, le=100000)
    media_quota_mb: int | None = Field(default=None, ge=0, le=10_000_000)


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    domain: str
    admin_name: str = Field(min_length=2, max_length=200)
    admin_email: EmailStr
    admin_password: str | None = Field(default=None, min_length=10, max_length=200, description="Leave empty to generate one.")
    timezone: str = Field(default="UTC", max_length=64)
    limits: Limits = Limits()
    _d = field_validator("domain")(clean_domain)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    limits: Limits | None = None


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class SupportStart(BaseModel):
    reason: str = Field(min_length=10, max_length=400, description="Why you need to sign in (shown in the log).")


class ResetPassword(BaseModel):
    password: str | None = Field(default=None, min_length=10, max_length=200, description="Leave empty to generate one.")


class Register(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    domain: str
    owner_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)
    business_type: Literal["RESORT", "HOTEL", "HOUSEBOAT", "TRAVEL_AGENCY", "OTHER"] = "RESORT"
    accept_terms: bool
    website: str | None = Field(default=None, max_length=200, description="Leave empty (spam trap).")
    _d = field_validator("domain")(clean_domain)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Please accept the terms to register.")
        return v
