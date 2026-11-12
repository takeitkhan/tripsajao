"""10-minute hold engine primitives.

Source of truth  : bookings row (status=HOLD, hold_expires_at) + exclusion constraint + per-property advisory lock.
Redis            : `hold:{tenant_id}:{booking_id}` with TTL = hold seconds. Its *expired* keyspace event is a fast
                   trigger for release. Events are fire-and-forget, so a Celery beat sweep is the guarantee.
All release paths funnel into `release_expired`, which is idempotent.
"""
import logging
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Unit, UnitType

log = logging.getLogger(__name__)


def hold_key(tenant_id: UUID | str, booking_id: UUID | str) -> str:
    return f"hold:{tenant_id}:{booking_id}"


def parse_hold_key(key: str) -> tuple[UUID, UUID] | None:
    parts = key.split(":")
    if len(parts) != 3 or parts[0] != "hold":
        return None
    try:
        return UUID(parts[1]), UUID(parts[2])
    except ValueError:
        return None


async def release_expired(session: AsyncSession, *, tenant_id: UUID | None = None, booking_id: UUID | None = None,
                          property_id: UUID | None = None) -> list[tuple[UUID, UUID, UUID]]:
    """Cancel HOLD bookings whose deadline has passed. Returns [(tenant_id, booking_id, unit_id)].
    Only ever touches rows that are still HOLD *and* expired -> safe to call from any number of racers."""
    stmt = update(Booking).where(Booking.status == BookingStatus.HOLD,
                                 Booking.hold_expires_at <= func.clock_timestamp())
    if tenant_id:
        stmt = stmt.where(Booking.tenant_id == tenant_id)
    if booking_id:
        stmt = stmt.where(Booking.id == booking_id)
    if property_id:
        stmt = stmt.where(Booking.property_id == property_id)
    stmt = stmt.values(status=BookingStatus.CANCELLED, cancel_reason="HOLD_EXPIRED").returning(
        Booking.tenant_id, Booking.id, Booking.unit_id).execution_options(synchronize_session=False)
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def assert_available(session: AsyncSession, unit: Unit, check_in, check_out) -> None:
    """Application-level overlap check, including whole-boat <-> cabin conflicts that a per-unit
    exclusion constraint cannot see. Caller must hold the property advisory lock."""
    from fastapi import HTTPException

    stmt = select(Booking.id).where(
        Booking.tenant_id == unit.tenant_id,
        Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        Booking.check_in < check_out, Booking.check_out > check_in).limit(1)
    if unit.type == UnitType.WHOLE_BOAT:
        stmt = stmt.where(Booking.property_id == unit.property_id)          # any cabin blocks a charter
    else:
        charter_ids = select(Unit.id).where(Unit.property_id == unit.property_id, Unit.type == UnitType.WHOLE_BOAT)
        stmt = stmt.where(or_(Booking.unit_id == unit.id, Booking.unit_id.in_(charter_ids)))   # charter blocks a cabin
    if (await session.execute(stmt)).first():
        raise HTTPException(409, "Selected dates are not available for this unit")
