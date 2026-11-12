from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CMSStatus, CMSType
from app.schemas.common import ORMModel
from app.schemas.inventory import MediaItem


class BlogPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_markdown: str
    excerpt: str | None = None
    cover_image: str | None = None
    tags: list[str] = []
    author: str | None = None


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    starts_at: datetime
    ends_at: datetime | None = None
    venue: str | None = None
    description: str | None = None
    cover_image: str | None = None
    registration_url: str | None = None


class GalleryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    items: list[MediaItem] = Field(min_length=1, max_length=500)


class PagePayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_markdown: str
    seo_title: str | None = None
    seo_description: str | None = None


class AnnouncementPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    message: str
    severity: Literal["info", "warning", "critical"] = "info"
    starts_at: datetime | None = None
    ends_at: datetime | None = None


PAYLOAD_MODELS: dict[CMSType, type[BaseModel]] = {
    CMSType.BLOG: BlogPayload, CMSType.EVENT: EventPayload, CMSType.GALLERY: GalleryPayload,
    CMSType.PAGE: PagePayload, CMSType.ANNOUNCEMENT: AnnouncementPayload,
}


class CMSCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=150)
    status: CMSStatus = CMSStatus.DRAFT
    payload: dict[str, Any]
    model_config = ConfigDict(json_schema_extra={"example": {
        "title": "Monsoon Getaway Offer", "status": "PUBLISHED",
        "payload": {"body_markdown": "# 20% off all cabins in July", "tags": ["offer"]}}})


class CMSUpdate(BaseModel):
    title: str | None = None
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=150)
    status: CMSStatus | None = None
    payload: dict[str, Any] | None = None


class CMSOut(ORMModel):
    id: UUID
    content_type: CMSType
    slug: str
    title: str
    status: CMSStatus
    payload: dict[str, Any] = Field(validation_alias="payload_json")
    published_at: datetime | None
    updated_at: datetime


class CompanyInfo(BaseModel):
    name: str | None = None
    tagline: str | None = None
    logo_url: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    social: dict[str, str] = {}
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    timezone: str | None = None
