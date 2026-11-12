from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MAX_TAGS = 20


def clean_tags(tags: list[str] | None) -> list[str]:
    """Trimmed, lower-case, no duplicates, each up to 30 characters."""
    out: list[str] = []
    for t in tags or []:
        t = " ".join(str(t).split()).lower()[:30]
        if t and t not in out:
            out.append(t)
    if len(out) > MAX_TAGS:
        raise ValueError(f"At most {MAX_TAGS} tags per customer")
    return out


class CustomerFilters(BaseModel):
    q: str | None = Field(default=None, max_length=100, description="Name, e-mail or phone contains this")
    tag: str | None = Field(default=None, max_length=30)
    source: str | None = Field(default=None, pattern="^(BOOKING|CONTACT|MANUAL)$")
    min_stays: int | None = Field(default=None, ge=0, description="At least this many confirmed bookings")
    max_stays: int | None = Field(default=None, ge=0)
    inactive_days: int | None = Field(default=None, ge=1, le=3650, description="Stayed before, but not in the last N days")
    sort: str = Field(default="recent", pattern="^(recent|spent|stays|name)$")


def customer_filters(q: str | None = Query(None, max_length=100), tag: str | None = Query(None, max_length=30),
                     source: str | None = Query(None, pattern="^(BOOKING|CONTACT|MANUAL)$"),
                     min_stays: int | None = Query(None, ge=0), max_stays: int | None = Query(None, ge=0),
                     inactive_days: int | None = Query(None, ge=1, le=3650),
                     sort: str = Query("recent", pattern="^(recent|spent|stays|name)$")) -> CustomerFilters:
    return CustomerFilters(q=q, tag=tag, source=source, min_stays=min_stays, max_stays=max_stays, inactive_days=inactive_days, sort=sort)


class CustomerOut(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    tags: list[str]
    notes: str | None
    source: str
    stays: int = Field(description="Confirmed bookings")
    cancelled: int
    total_spent: Decimal
    currency: str
    last_stay: date | None = Field(description="Check-out date of the latest confirmed stay")
    next_stay: date | None
    last_booked_at: datetime | None
    created_at: datetime


class CustomerBooking(BaseModel):
    id: UUID
    booking_ref: str | None
    property: str
    unit: str
    check_in: date
    check_out: date
    status: str
    total_amount: Decimal
    paid_amount: Decimal
    currency: str


class CustomerDetail(CustomerOut):
    bookings: list[CustomerBooking]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    tags: list[str] = []
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return clean_tags(v)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return None if v is None else clean_tags(v)


class BulkTag(BaseModel):
    ids: list[UUID] | None = Field(default=None, max_length=1000, description="These customers; or leave empty and send `filters` for everyone matching")
    filters: CustomerFilters | None = None
    add: list[str] = []
    remove: list[str] = []

    @field_validator("add", "remove")
    @classmethod
    def _tags(cls, v):
        return clean_tags(v)


class BulkTagResult(BaseModel):
    changed: int


class TagCount(BaseModel):
    tag: str
    customers: int
