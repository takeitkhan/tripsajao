"""Seat bookings on events: hold -> customer pays by hand and sends proof -> business confirms (or rejects / cancels).

Seats count as taken while a booking is CONFIRMED or PAYMENT_SUBMITTED, or is a HOLD whose timer (database clock) has not run out.
Every change to one event's seats happens under a lock on that event row, so two people can never take the last seat."""
import hashlib
import hmac
import secrets
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, literal_column, or_, select, text, update

from app.core.deps import TenantContext
from app.models import CommissionType, EventBooking, LedgerType, Partner, TourEvent
from app.services.ledger import add_entry
from app.services.pricing import ZERO, q

HOLD_STATES_COUNTED = ("CONFIRMED", "PAYMENT_SUBMITTED")


def hold_seconds(ctx: TenantContext) -> int:
    return int(ctx.tenant.settings_json.get("event_hold_seconds", ctx.tenant.settings_json.get("hold_seconds", 600)))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def counted():
    """SQL condition: this booking is using up seats right now."""
    return or_(EventBooking.status.in_(HOLD_STATES_COUNTED),
               (EventBooking.status == "HOLD") & (EventBooking.hold_expires_at > func.clock_timestamp()))


async def seats_taken(session, tenant_id: UUID, event_ids: list[UUID]) -> dict[UUID, int]:
    if not event_ids:
        return {}
    rows = (await session.execute(select(EventBooking.event_id, func.coalesce(func.sum(EventBooking.seats), 0))
                                  .where(EventBooking.tenant_id == tenant_id, EventBooking.event_id.in_(event_ids), counted())
                                  .group_by(EventBooking.event_id))).all()
    return {r[0]: int(r[1]) for r in rows}


async def expire_stale(session, tenant_id: UUID) -> None:
    await session.execute(update(EventBooking).where(EventBooking.tenant_id == tenant_id, EventBooking.status == "HOLD",
                                                      EventBooking.hold_expires_at <= func.clock_timestamp())
                          .values(status="EXPIRED", hold_expires_at=None))


def event_commission(partner: Partner, total: Decimal, seats: int) -> Decimal:
    if partner.commission_type == CommissionType.PERCENT:
        return q(total * partner.commission_value / Decimal(100))
    return q(min(partner.commission_value * seats, total))      # flat amount per seat, never more than the sale


async def lock_event(session, tenant_id: UUID, event_id: UUID) -> TourEvent:
    ev = (await session.execute(select(TourEvent).where(TourEvent.id == event_id, TourEvent.tenant_id == tenant_id)
                                .with_for_update())).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Event not found")
    return ev


async def create_hold(ctx: TenantContext, event_id: UUID, seats: int, customer: dict, partner: Partner | None) -> tuple[EventBooking, str, TourEvent]:
    s = ctx.session
    ev = await lock_event(s, ctx.tenant.id, event_id)
    if ctx.principal.kind == "api_client" and ev.status != "PUBLISHED":
        raise HTTPException(404, "Event not found")
    if ev.status != "PUBLISHED":
        raise HTTPException(409, "This event is not open for booking")
    if ev.starts_on < date.today():
        raise HTTPException(409, "This event has already started")
    if ev.seats is not None:
        taken = (await seats_taken(s, ctx.tenant.id, [ev.id])).get(ev.id, 0)
        if taken + seats > ev.seats:
            left = max(ev.seats - taken, 0)
            raise HTTPException(409, "This event is full" if left == 0 else f"Only {left} seat{'s' if left != 1 else ''} left")
    total = q(Decimal(ev.price) * seats)
    token = secrets.token_urlsafe(24)
    ttl = hold_seconds(ctx)
    b = EventBooking(tenant_id=ctx.tenant.id, event_id=ev.id, booking_ref="EV" + secrets.token_hex(4).upper(), token_hash=token_hash(token),
                     customer_info_json=customer, seats=seats, unit_price=q(Decimal(ev.price)), total_amount=total, paid_amount=ZERO,
                     currency=ev.currency, status="HOLD", partner_id=partner.id if partner else None,
                     commission_amount=event_commission(partner, total, seats) if partner else ZERO,
                     hold_expires_at=literal_column(f"clock_timestamp() + interval '{ttl} seconds'"), proofs_json=[], payments_json=[])
    # the guest becomes a customer (once, by e-mail) so the business can find them in Customers
    email = customer["email"].strip().lower()
    cid = (await s.execute(text("""INSERT INTO customers (id, tenant_id, email, name, phone, source, created_at, updated_at)
        VALUES (gen_random_uuid(), :t, :e, :n, :p, 'BOOKING', now(), now()) ON CONFLICT (tenant_id, email) DO UPDATE SET email = excluded.email
        RETURNING id"""), {"t": ctx.tenant.id, "e": email, "n": customer["name"][:200], "p": customer["phone"][:40]})).scalar_one()
    b.customer_id = cid
    s.add(b)
    await s.flush()
    await s.refresh(b)
    return b, token, ev


async def get_for_guest(ctx: TenantContext, ref: str, token: str, *, lock: bool = False) -> EventBooking:
    stmt = select(EventBooking).where(EventBooking.tenant_id == ctx.tenant.id, EventBooking.booking_ref == ref)
    if lock:
        stmt = stmt.with_for_update()
    b = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if b is None or not hmac.compare_digest(b.token_hash, token_hash(token or "")):
        raise HTTPException(404, "Booking not found")          # same answer for a wrong ref and a wrong token
    return b


async def sync_event_commission(session, b: EventBooking, *, cancelled: bool = False) -> None:
    if b.partner_id is None or b.commission_amount <= 0:
        return
    target = ZERO if cancelled or b.total_amount <= 0 else q(b.commission_amount * min(b.paid_amount / b.total_amount, Decimal(1)))
    credited = (await session.execute(
        text("SELECT coalesce(sum(credit - debit), 0) FROM partner_ledgers WHERE event_booking_id = :b AND transaction_type IN ('COMMISSION', 'COMMISSION_REVERSAL')"),
        {"b": b.id})).scalar_one()
    delta = q(target - Decimal(credited))
    if delta > 0:
        await add_entry(session, tenant_id=b.tenant_id, partner_id=b.partner_id, event_booking_id=b.id, transaction_type=LedgerType.COMMISSION,
                        credit=delta, note=f"Commission on {b.booking_ref}")
    elif delta < 0:
        await add_entry(session, tenant_id=b.tenant_id, partner_id=b.partner_id, event_booking_id=b.id, transaction_type=LedgerType.COMMISSION_REVERSAL,
                        debit=-delta, note=f"Reversal on {b.booking_ref}")
