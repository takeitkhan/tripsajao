import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, created_col, enum_col, pk, tenant_fk, updated_col
from app.models.enums import PropertyType, UnitStatus, UnitType


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_properties_tenant_id_id"),  # target for composite FKs
        UniqueConstraint("tenant_id", "slug", name="uq_properties_tenant_slug"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    type: Mapped[PropertyType] = enum_col(PropertyType)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(300))
    # description, amenities[] (custom-icon facilities), media[] (photos/videos), address, extra
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict,
                                                          server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()

    units: Mapped[list["Unit"]] = relationship(back_populates="property", viewonly=True, lazy="raise")


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_units_tenant_id_id"),
        ForeignKeyConstraint(["tenant_id", "property_id"], ["properties.tenant_id", "properties.id"],
                             name="fk_units_property_same_tenant", ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "property_id", "unit_name", name="uq_units_property_name"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    property_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    unit_name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[UnitType] = enum_col(UnitType)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default=text("2"))
    # [{"name":"AC","icon":"wind","type":"lucide"}, {"name":"Balcony","icon":"https://cdn.x/b.svg","type":"svg"}]
    facilities_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    media_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # grid:  {"floor":1,"row":0,"col":2,"row_span":1,"col_span":1}   boat: {"x":80,"y":30,"w":50,"h":28}
    layout_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[UnitStatus] = enum_col(UnitStatus, default=UnitStatus.AVAILABLE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()

    property: Mapped["Property"] = relationship(back_populates="units", viewonly=True, lazy="raise")
    pricing_rule: Mapped[Optional["PricingRule"]] = relationship(back_populates="unit", viewonly=True, lazy="raise")


class PricingRule(Base):
    __tablename__ = "pricing_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_id", name="uq_pricing_rules_tenant_unit"),
        ForeignKeyConstraint(["tenant_id", "unit_id"], ["units.tenant_id", "units.id"],
                             name="fk_pricing_rules_unit_same_tenant", ondelete="CASCADE"),
        CheckConstraint("weekday_price >= 0 AND weekend_price >= 0", name="prices_non_negative"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    unit_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    weekday_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    weekend_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # {"weekend_days":[4,5], "rules":[{name, category, start_date, end_date, kind, value, applies_to, priority}]}
    seasonal_price_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                                server_default=text("'{}'::jsonb"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default=text("'USD'"))
    updated_at: Mapped[datetime] = updated_col()

    unit: Mapped["Unit"] = relationship(back_populates="pricing_rule", viewonly=True, lazy="raise")
