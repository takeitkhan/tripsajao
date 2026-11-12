import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.models.enums import PropertyType, UnitStatus, UnitType
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- facilities (custom icons)
_LUCIDE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_CSS_CLASSES = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*( [a-z0-9]+(-[a-z0-9]+)*){0,4}$")


class Facility(BaseModel):
    """One amenity with a custom icon.

    type=svg          -> icon is an https URL to an .svg file
    type=lucide       -> icon is a Lucide icon name, e.g. "wind"
    type=fontawesome  -> icon is FA classes, e.g. "fa-solid fa-wind"
    type=class        -> icon is any CSS class string for the tenant's own icon font
    """
    name: str = Field(min_length=1, max_length=60)
    icon: str = Field(min_length=1, max_length=300)
    type: Literal["svg", "lucide", "fontawesome", "class"] = "lucide"
    category: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _validate_icon(self):
        if self.type == "svg":
            u = urlparse(self.icon)
            if u.scheme != "https" or not u.netloc or not u.path.lower().endswith(".svg"):
                raise ValueError("svg icons must be https URLs ending in .svg")
        elif self.type == "lucide":
            if not _LUCIDE.match(self.icon):
                raise ValueError("lucide icon names are lower-case kebab-case, e.g. 'wind'")
        elif not _CSS_CLASSES.match(self.icon):
            raise ValueError("icon classes must be space separated lower-case class names")
        return self


def _unique_names(items: list[Facility]) -> list[Facility]:
    seen: set[str] = set()
    for f in items:
        k = f.name.strip().lower()
        if k in seen:
            raise ValueError(f"duplicate facility '{f.name}'")
        seen.add(k)
    return items


Facilities = Annotated[list[Facility], Field(max_length=60), AfterValidator(_unique_names)]

FACILITY_PRESETS: list[Facility] = [
    Facility(name="AC", icon="wind", category="comfort"),
    Facility(name="Balcony", icon="door-open", category="room"),
    Facility(name="Towels", icon="bath", category="bathroom"),
    Facility(name="Iron", icon="shirt", category="room"),
    Facility(name="Wardrobe", icon="archive", category="room"),
    Facility(name="Attached Bath", icon="shower-head", category="bathroom"),
    Facility(name="Sofa", icon="sofa", category="room"),
    Facility(name="Wi-Fi", icon="wifi", category="connectivity"),
    Facility(name="TV", icon="tv", category="entertainment"),
    Facility(name="Breakfast", icon="coffee", category="food"),
]


class MediaItem(BaseModel):
    type: Literal["photo", "video"]
    url: str = Field(pattern=r"^https?://\S+$", max_length=500)
    caption: str | None = Field(default=None, max_length=200)
    alt: str | None = Field(default=None, max_length=300)                 # for accessibility / SEO
    thumbnail_url: str | None = Field(default=None, pattern=r"^https?://\S+$", max_length=500)
    asset_id: UUID | None = None                                          # set when picked from the media library


# ---------------------------------------------------------------- properties & units
class PropertyMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str | None = None
    amenities: Facilities = []
    media: list[MediaItem] = Field(default=[], max_length=100)
    address: str | None = None


_SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class PropertyCreate(BaseModel):
    type: PropertyType
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=_SLUG, max_length=100)
    location: str | None = Field(default=None, max_length=300)
    metadata: PropertyMetadata = PropertyMetadata()
    model_config = ConfigDict(json_schema_extra={"example": {
        "type": "HOUSEBOAT", "name": "Lotus Houseboat", "slug": "lotus-houseboat", "location": "Alleppey, Kerala",
        "metadata": {"description": "3-cabin luxury houseboat", "amenities": [{"name": "AC", "icon": "wind", "type": "lucide"}],
                     "media": [{"type": "photo", "url": "https://cdn.example.com/lotus.jpg"}]}}})


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    slug: str | None = Field(default=None, pattern=_SLUG, max_length=100)
    location: str | None = None
    metadata: PropertyMetadata | None = None
    is_active: bool | None = None


class PropertyOut(ORMModel):
    id: UUID
    type: PropertyType
    name: str
    slug: str
    location: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    is_active: bool


_GRID_TYPES = {UnitType.ROOM, UnitType.COTTAGE, UnitType.DUPLEX}
_BOAT_TYPES = {UnitType.CABIN, UnitType.WHOLE_BOAT}


def unit_type_allowed(prop_type: PropertyType, unit_type: UnitType) -> bool:
    return unit_type in (_BOAT_TYPES if prop_type == PropertyType.HOUSEBOAT else _GRID_TYPES)


class UnitCreate(BaseModel):
    unit_name: str = Field(min_length=1, max_length=120)
    type: UnitType
    capacity: int = Field(default=2, ge=1, le=100)
    facilities: Facilities = []
    media: list[MediaItem] = Field(default=[], max_length=50)
    layout: dict[str, Any] | None = None
    model_config = ConfigDict(json_schema_extra={"example": {
        "unit_name": "Cabin 1", "type": "CABIN", "capacity": 2,
        "facilities": [{"name": "AC", "icon": "wind", "type": "lucide"},
                       {"name": "Balcony", "icon": "https://cdn.example.com/icons/balcony.svg", "type": "svg"}],
        "layout": {"x": 80, "y": 30, "w": 50, "h": 28}}})


class UnitUpdate(BaseModel):
    unit_name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=100)
    facilities: Facilities | None = None
    media: list[MediaItem] | None = None
    layout: dict[str, Any] | None = None
    status: UnitStatus | None = None
    is_active: bool | None = None


class UnitOut(ORMModel):
    id: UUID
    property_id: UUID
    unit_name: str
    type: UnitType
    capacity: int
    facilities: list[Any] = Field(validation_alias="facilities_json")
    media: list[Any] = Field(validation_alias="media_json")
    layout: dict[str, Any] | None = Field(validation_alias="layout_json")
    status: UnitStatus
    is_active: bool


# ---------------------------------------------------------------- pricing
class SeasonalRule(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: Literal["SEASON", "HOLIDAY"] = "SEASON"
    start_date: date
    end_date: date                       # inclusive; a single-day holiday has start == end
    kind: Literal["SURCHARGE_PERCENT", "SURCHARGE_FLAT", "OVERRIDE"]
    value: Decimal = Field(ge=0)
    applies_to: Literal["ALL", "WEEKDAY", "WEEKEND"] = "ALL"
    priority: int = 0                    # only used to choose between several OVERRIDE rules

    @model_validator(mode="after")
    def _range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on/after start_date")
        return self


class SeasonalConfig(BaseModel):
    weekend_days: list[int] = Field(default=[4, 5], description="Mon=0 ... Sun=6; default Fri+Sat nights")
    rules: list[SeasonalRule] = Field(default=[], max_length=200)

    @model_validator(mode="after")
    def _days(self):
        if any(d < 0 or d > 6 for d in self.weekend_days):
            raise ValueError("weekend_days must be within 0..6")
        return self


class PricingRuleIn(BaseModel):
    weekday_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    weekend_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    seasonal: SeasonalConfig = SeasonalConfig()
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    model_config = ConfigDict(json_schema_extra={"example": {
        "weekday_price": "4500.00", "weekend_price": "6000.00", "currency": "INR",
        "seasonal": {"weekend_days": [4, 5], "rules": [
            {"name": "Christmas", "category": "HOLIDAY", "start_date": "2026-12-24", "end_date": "2026-12-26",
             "kind": "SURCHARGE_PERCENT", "value": "25", "applies_to": "ALL"}]}}})


class PricingRuleOut(ORMModel):
    unit_id: UUID
    weekday_price: Decimal
    weekend_price: Decimal
    seasonal: dict[str, Any] = Field(validation_alias="seasonal_price_json")
    currency: str


class QuoteRequest(BaseModel):
    unit_id: UUID
    check_in: date
    check_out: date
    model_config = ConfigDict(json_schema_extra={"example": {
        "unit_id": "00000000-0000-0000-0000-000000000000", "check_in": "2026-12-24", "check_out": "2026-12-27"}})


class NightPriceOut(BaseModel):
    night: date
    day_type: Literal["WEEKDAY", "WEEKEND"]
    base_price: Decimal
    applied_rules: list[str]
    price: Decimal


class QuoteOut(BaseModel):
    unit_id: UUID
    currency: str
    nights: list[NightPriceOut]
    total: Decimal
