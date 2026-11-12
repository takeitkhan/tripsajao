import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Float, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_col, enum_col, pk, tenant_fk
from app.models.enums import MediaKind, MediaSource


class MediaAsset(Base):
    """One photo or video in a tenant's media library. Files live in the storage backend under `storage_key`."""
    __tablename__ = "media_assets"
    __table_args__ = (Index("ix_media_assets_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    kind: Mapped[MediaKind] = enum_col(MediaKind)
    source: Mapped[MediaSource] = enum_col(MediaSource, default=MediaSource.UPLOAD)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    alt_text: Mapped[Optional[str]] = mapped_column(String(300))
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    original_name: Mapped[Optional[str]] = mapped_column(String(255))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    storage_key: Mapped[Optional[str]] = mapped_column(String(300))       # UPLOAD only
    thumb_key: Mapped[Optional[str]] = mapped_column(String(300))         # small preview, if one could be made
    external_url: Mapped[Optional[str]] = mapped_column(String(500))      # EXTERNAL only
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column()
    created_at: Mapped[datetime] = created_col()
