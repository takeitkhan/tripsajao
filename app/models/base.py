import uuid

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, MetaData, Numeric, func, text
from sqlalchemy.orm import DeclarativeBase, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


Money = Numeric(12, 2)
TZ = DateTime(timezone=True)


def pk():
    return mapped_column(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))


def tenant_fk():
    """Explicit tenant discriminator. RLS policies key off this column."""
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)


def enum_col(enum_cls, **kw):
    return mapped_column(
        SAEnum(enum_cls, native_enum=False, length=24, validate_strings=True,
               values_callable=lambda e: [m.value for m in e]),
        nullable=False, **kw)


def created_col():
    return mapped_column(TZ, server_default=func.now(), nullable=False)


def updated_col():
    return mapped_column(TZ, server_default=func.now(), onupdate=func.now(), nullable=False)
