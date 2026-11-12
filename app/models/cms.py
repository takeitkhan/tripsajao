import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TZ, created_col, enum_col, pk, tenant_fk, updated_col
from app.models.enums import CMSStatus, CMSType


class CMSContent(Base):
    __tablename__ = "cms_content"
    __table_args__ = (UniqueConstraint("tenant_id", "content_type", "slug", name="uq_cms_tenant_type_slug"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    content_type: Mapped[CMSType] = enum_col(CMSType)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[CMSStatus] = enum_col(CMSStatus, default=CMSStatus.DRAFT)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    published_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
