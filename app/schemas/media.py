from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import MediaKind, MediaSource

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class MediaOut(BaseModel):
    id: UUID
    kind: MediaKind
    source: MediaSource
    title: str
    alt_text: str | None
    tags: list[str]
    original_name: str | None
    mime_type: str | None
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: float | None
    url: str = Field(description="Public address of the file (or the video link). Use this on your website.")
    thumbnail_url: str | None = Field(description="Small preview picture, when one exists.")
    provider: Literal["upload", "youtube", "vimeo", "file"] = "upload"
    embed_url: str | None = Field(default=None, description="For YouTube and Vimeo links: the address to put in an iframe.")
    created_at: datetime


class MediaLink(BaseModel):
    url: str = Field(max_length=500, description="A YouTube or Vimeo link, or a direct link to an .mp4 / .webm file.")
    title: str | None = Field(default=None, max_length=200)
    alt_text: str | None = Field(default=None, max_length=300)
    tags: list[Tag] = Field(default=[], max_length=20)
    model_config = ConfigDict(json_schema_extra={"example": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Resort tour"}})


class MediaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    alt_text: str | None = Field(default=None, max_length=300)
    tags: list[Tag] | None = Field(default=None, max_length=20)


class UsagePlace(BaseModel):
    kind: str
    name: str
    id: UUID | None = None


class MediaUsage(BaseModel):
    count: int
    places: list[UsagePlace]


class MediaSummary(BaseModel):
    images: int
    videos: int
    used_bytes: int
    quota_bytes: int
    max_image_bytes: int
    max_video_bytes: int
    allowed: dict[str, list[str]]
