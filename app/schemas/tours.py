from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel

Money = Decimal
CURRENCY = Field(default="BDT", pattern=r"^[A-Z]{3}$")
SLUG = Field(default=None, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=150)
VENDOR_CATEGORIES = ("RESORT", "RESTAURANT", "GUIDE", "CHANDER_GARI", "JEEP", "CNG", "BOAT", "OTHER")
RATE_UNITS = ("PER_NIGHT", "PER_PERSON", "PER_DAY", "PER_TRIP", "PER_MEAL", "PER_ROOM", "PER_UNIT")
Category = Literal["RESORT", "RESTAURANT", "GUIDE", "CHANDER_GARI", "JEEP", "CNG", "BOAT", "OTHER"]
Unit = Literal["PER_NIGHT", "PER_PERSON", "PER_DAY", "PER_TRIP", "PER_MEAL", "PER_ROOM", "PER_UNIT"]


class Day(BaseModel):
    day: int = Field(ge=1, le=60)
    title: str = Field(min_length=1, max_length=200)
    details: Optional[str] = Field(default=None, max_length=3000)


def _texts(v: list[str]) -> list[str]:
    seen: list[str] = []
    for x in v:
        x = (x or "").strip()[:300]
        if x and x not in seen:
            seen.append(x)
    return seen[:60]


_LISTS = ("inclusions", "exclusions", "trip_types", "other_transport", "health_rules", "warnings", "essentials", "payment_methods")
_tidy = field_validator(*_LISTS, check_fields=False)(lambda cls, v: None if v is None else _texts(v))


def _photos(v):
    return None if v is None else [x.strip() for x in v if x and x.strip()][:30]


class TripBody(BaseModel):
    """What a package and an event have in common."""
    summary: Optional[str] = Field(default=None, max_length=600)
    description: Optional[str] = Field(default=None, max_length=20000)
    location: Optional[str] = Field(default=None, max_length=200)
    itinerary: list[Day] = Field(default_factory=list, max_length=60)
    inclusions: list[str] = Field(default_factory=list, max_length=60)
    exclusions: list[str] = Field(default_factory=list, max_length=60)
    cover_image: Optional[str] = Field(default=None, max_length=1000)
    pickup_location: Optional[str] = Field(default=None, max_length=300, description="Where the trip starts from")
    accommodation: Optional[str] = Field(default=None, max_length=3000)
    trip_types: list[str] = Field(default_factory=list, max_length=20, description="For example relax, trekking")
    bus_type: Optional[str] = Field(default=None, max_length=80)
    other_transport: list[str] = Field(default_factory=list, max_length=30, description="For example CNG, jeep, boat")
    health_rules: list[str] = Field(default_factory=list, max_length=60)
    warnings: list[str] = Field(default_factory=list, max_length=60)
    essentials: list[str] = Field(default_factory=list, max_length=60, description="What to bring")
    photos: list[str] = Field(default_factory=list, max_length=30, description="Photo addresses, the first one is used on cards")

    _i = _tidy
    _p = field_validator("photos")(lambda cls, v: _photos(v))


# ---------- packages
class PackageIn(TripBody):
    title: str = Field(min_length=1, max_length=300)
    slug: Optional[str] = SLUG
    duration_days: int = Field(default=1, ge=1, le=60)
    starting_price: Money = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2, description="'Starting from' price per person")
    currency: str = CURRENCY
    is_published: bool = False
    model_config = ConfigDict(json_schema_extra={"example": {
        "title": "Sajek Valley 3 days", "summary": "Clouds, hills and a night in a cottage", "location": "Sajek", "duration_days": 3,
        "starting_price": "5000.00", "currency": "BDT", "is_published": True,
        "itinerary": [{"day": 1, "title": "Dhaka to Sajek", "details": "Night bus, breakfast on the way"}],
        "inclusions": ["Cottage stay", "Breakfast", "Chander gari"], "exclusions": ["Lunch and dinner"]}})


class PackageUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    slug: Optional[str] = SLUG
    summary: Optional[str] = Field(default=None, max_length=600)
    description: Optional[str] = Field(default=None, max_length=20000)
    location: Optional[str] = Field(default=None, max_length=200)
    duration_days: Optional[int] = Field(default=None, ge=1, le=60)
    starting_price: Optional[Money] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    itinerary: Optional[list[Day]] = Field(default=None, max_length=60)
    inclusions: Optional[list[str]] = Field(default=None, max_length=60)
    exclusions: Optional[list[str]] = Field(default=None, max_length=60)
    cover_image: Optional[str] = Field(default=None, max_length=1000)
    is_published: Optional[bool] = None
    pickup_location: Optional[str] = Field(default=None, max_length=300)
    accommodation: Optional[str] = Field(default=None, max_length=3000)
    trip_types: Optional[list[str]] = Field(default=None, max_length=20)
    bus_type: Optional[str] = Field(default=None, max_length=80)
    other_transport: Optional[list[str]] = Field(default=None, max_length=30)
    health_rules: Optional[list[str]] = Field(default=None, max_length=60)
    warnings: Optional[list[str]] = Field(default=None, max_length=60)
    essentials: Optional[list[str]] = Field(default=None, max_length=60)
    photos: Optional[list[str]] = Field(default=None, max_length=30)

    _i = _tidy
    _p = field_validator("photos")(lambda cls, v: _photos(v))


class PackageOut(ORMModel):
    id: UUID
    slug: str
    title: str
    summary: Optional[str]
    description: Optional[str]
    location: Optional[str]
    duration_days: int
    starting_price: Money
    currency: str
    itinerary: list[Any]
    inclusions: list[str]
    exclusions: list[str]
    cover_image: Optional[str]
    pickup_location: Optional[str]
    accommodation: Optional[str]
    trip_types: list[str]
    bus_type: Optional[str]
    other_transport: list[str]
    health_rules: list[str]
    warnings: list[str]
    essentials: list[str]
    photos: list[str]
    is_published: bool
    updated_at: datetime


# ---------- events
class EventIn(TripBody):
    title: str = Field(min_length=1, max_length=300)
    slug: Optional[str] = SLUG
    starts_on: date
    ends_on: Optional[date] = None
    price: Money = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2, description="Price per person")
    currency: str = CURRENCY
    seats: Optional[int] = Field(default=None, ge=1, le=100000)
    package_id: Optional[UUID] = None
    payment_methods: list[str] = Field(default_factory=list, max_length=20, description="For example bKash, Nagad, bank transfer")
    status: Literal["DRAFT", "PUBLISHED", "CLOSED"] = "DRAFT"


class EventFromPackage(BaseModel):
    starts_on: date
    ends_on: Optional[date] = Field(default=None, description="Leave empty to use the package length")
    title: Optional[str] = Field(default=None, max_length=300, description="Leave empty to use the package title")
    price: Optional[Money] = Field(default=None, ge=0, max_digits=12, decimal_places=2, description="Leave empty to use the package's 'starting from' price")
    seats: Optional[int] = Field(default=None, ge=1, le=100000)
    payment_methods: list[str] = Field(default_factory=list, max_length=20)
    photos: Optional[list[str]] = Field(default=None, max_length=30, description="Leave empty to use the package photos")
    publish: bool = True

    _i = _tidy


class EventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    slug: Optional[str] = SLUG
    summary: Optional[str] = Field(default=None, max_length=600)
    description: Optional[str] = Field(default=None, max_length=20000)
    location: Optional[str] = Field(default=None, max_length=200)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    price: Optional[Money] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    seats: Optional[int] = Field(default=None, ge=1, le=100000)
    itinerary: Optional[list[Day]] = Field(default=None, max_length=60)
    inclusions: Optional[list[str]] = Field(default=None, max_length=60)
    exclusions: Optional[list[str]] = Field(default=None, max_length=60)
    cover_image: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Literal["DRAFT", "PUBLISHED", "CLOSED"]] = None
    payment_methods: Optional[list[str]] = Field(default=None, max_length=20)
    pickup_location: Optional[str] = Field(default=None, max_length=300)
    accommodation: Optional[str] = Field(default=None, max_length=3000)
    trip_types: Optional[list[str]] = Field(default=None, max_length=20)
    bus_type: Optional[str] = Field(default=None, max_length=80)
    other_transport: Optional[list[str]] = Field(default=None, max_length=30)
    health_rules: Optional[list[str]] = Field(default=None, max_length=60)
    warnings: Optional[list[str]] = Field(default=None, max_length=60)
    essentials: Optional[list[str]] = Field(default=None, max_length=60)
    photos: Optional[list[str]] = Field(default=None, max_length=30)

    _i = _tidy
    _p = field_validator("photos")(lambda cls, v: _photos(v))


class EventOut(ORMModel):
    id: UUID
    slug: str
    title: str
    summary: Optional[str]
    description: Optional[str]
    location: Optional[str]
    starts_on: date
    ends_on: date
    price: Money
    currency: str
    seats: Optional[int]
    package_id: Optional[UUID]
    itinerary: list[Any]
    inclusions: list[str]
    exclusions: list[str]
    cover_image: Optional[str]
    pickup_location: Optional[str]
    accommodation: Optional[str]
    trip_types: list[str]
    bus_type: Optional[str]
    other_transport: list[str]
    health_rules: list[str]
    warnings: list[str]
    essentials: list[str]
    photos: list[str]
    payment_methods: list[str]
    seats_left: Optional[int] = None
    status: str
    published_at: Optional[datetime]
    updated_at: datetime


# ---------- vendors and rates
class VendorIn(BaseModel):
    category: Category
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=60)
    email: Optional[str] = Field(default=None, max_length=320)
    address: Optional[str] = Field(default=None, max_length=400)
    notes: Optional[str] = Field(default=None, max_length=4000)
    is_active: bool = True


class VendorUpdate(BaseModel):
    category: Optional[Category] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=60)
    email: Optional[str] = Field(default=None, max_length=320)
    address: Optional[str] = Field(default=None, max_length=400)
    notes: Optional[str] = Field(default=None, max_length=4000)
    is_active: Optional[bool] = None


class RateIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    unit: Unit = "PER_UNIT"
    price: Money = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = CURRENCY
    notes: Optional[str] = Field(default=None, max_length=500)


class RateUpdate(BaseModel):
    item: Optional[str] = Field(default=None, min_length=1, max_length=200)
    unit: Optional[Unit] = None
    price: Optional[Money] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    notes: Optional[str] = Field(default=None, max_length=500)


class RateOut(ORMModel):
    id: UUID
    vendor_id: UUID
    item: str
    unit: str
    price: Money
    currency: str
    notes: Optional[str]
    updated_at: datetime


class RateFound(RateOut):
    vendor_name: str
    category: str
    location: str


class VendorOut(ORMModel):
    id: UUID
    category: str
    name: str
    location: str
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    notes: Optional[str]
    is_active: bool
    rate_count: int = 0


class VendorDetail(VendorOut):
    rates: list[RateOut] = []


# ---------- budgets
class BudgetLine(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    vendor_id: Optional[UUID] = None
    vendor_name: Optional[str] = Field(default=None, max_length=200)
    unit: Optional[str] = Field(default=None, max_length=30, description="Shown beside the price, such as 'per night'")
    qty: Decimal = Field(default=Decimal(1), ge=0, max_digits=10, decimal_places=2)
    unit_price: Money = Field(ge=0, max_digits=12, decimal_places=2)
    per_person: bool = Field(default=False, description="True: the line is multiplied by the number of people too")
    note: Optional[str] = Field(default=None, max_length=300)


class BudgetIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    client_name: Optional[str] = Field(default=None, max_length=200)
    client_phone: Optional[str] = Field(default=None, max_length=60)
    event_id: Optional[UUID] = None
    package_id: Optional[UUID] = None
    people: int = Field(default=1, ge=1, le=100000)
    currency: str = CURRENCY
    lines: list[BudgetLine] = Field(default_factory=list, max_length=100)
    margin_percent: Decimal = Field(default=Decimal(0), ge=0, le=500, max_digits=6, decimal_places=2)
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Literal["DRAFT", "SENT", "WON", "LOST"] = "DRAFT"


class BudgetUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    client_name: Optional[str] = Field(default=None, max_length=200)
    client_phone: Optional[str] = Field(default=None, max_length=60)
    event_id: Optional[UUID] = None
    package_id: Optional[UUID] = None
    people: Optional[int] = Field(default=None, ge=1, le=100000)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    lines: Optional[list[BudgetLine]] = Field(default=None, max_length=100)
    margin_percent: Optional[Decimal] = Field(default=None, ge=0, le=500, max_digits=6, decimal_places=2)
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["DRAFT", "SENT", "WON", "LOST"]] = None


class BudgetLineOut(BudgetLine):
    line_total: Money


class BudgetTotals(BaseModel):
    cost_total: Money
    margin_amount: Money
    sell_total: Money
    cost_per_person: Money
    sell_per_person: Money


class BudgetOut(BudgetTotals):
    id: UUID
    title: str
    client_name: Optional[str]
    client_phone: Optional[str]
    event_id: Optional[UUID]
    package_id: Optional[UUID]
    people: int
    currency: str
    lines: list[BudgetLineOut]
    margin_percent: Decimal
    notes: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class BudgetRow(BaseModel):
    id: UUID
    title: str
    client_name: Optional[str]
    people: int
    currency: str
    cost_total: Money
    sell_total: Money
    margin_percent: Decimal
    status: str
    updated_at: datetime
