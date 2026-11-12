import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import TenantContext, authorize, get_or_404, paginate
from app.core.redis import get_redis
from app.models import Booking, BookingStatus, Property, UnitType
from app.schemas.booking import (AvailableUnit, BookingOut, CancelRequest, ConfirmOut, ConfirmRequest, HoldOut,
                                 HoldRequest)
from app.schemas.common import Page, Pagination
from app.services import booking as svc
from app.services.attribution import resolve_partner
from app.services.events import publish
from app.services.holds import hold_key
from app.services.pricing import q
from app.services.visual import live_status
from app.services.pricing import quote_for_unit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/availability", response_model=list[AvailableUnit], summary="Units available for a date range, with total price")
async def availability(property_id: UUID, check_in: date, check_out: date, guests: int = Query(1, ge=1),
                       ctx: TenantContext = Depends(authorize("availability:read"))):
    if check_out <= check_in:
        raise HTTPException(422, "check_out must be after check_in")
    await get_or_404(ctx, Property, property_id, "Property")
    units, live = await live_status(ctx.session, ctx.tenant.id, property_id, check_in, check_out)
    out = []
    for u in units:
        if live[u.id]["status"] != "AVAILABLE" or u.capacity < guests:
            continue
        try:
            stay = await quote_for_unit(ctx.session, ctx.tenant.id, u.id, check_in, check_out)
        except HTTPException:
            continue                       # unit without pricing is not sellable
        out.append(AvailableUnit(unit_id=u.id, unit_name=u.unit_name, unit_type=u.type.value, capacity=u.capacity,
                                 facilities=u.facilities_json, currency=stay.currency, total=stay.total))
    return out


@router.post("/hold", response_model=HoldOut, status_code=status.HTTP_201_CREATED,
             summary="Start checkout: lock the unit for 10 minutes (partner auto-attributed from cookie)")
async def hold(body: HoldRequest, request: Request, ctx: TenantContext = Depends(authorize("bookings:create"))):
    partner = await resolve_partner(ctx.session, ctx.tenant.id, request)
    booking = await svc.create_hold(ctx, body, partner)
    ttl = svc.hold_seconds(ctx)
    deposit = svc.deposit_for(ctx, booking.total_amount)
    out = HoldOut(booking_id=booking.id, booking_ref=booking.booking_ref, status=booking.status, unit_id=booking.unit_id,
                  check_in=booking.check_in, check_out=booking.check_out,
                  nights=(booking.check_out - booking.check_in).days, currency=booking.currency,
                  total_amount=booking.total_amount, deposit_amount=deposit, hold_expires_at=booking.hold_expires_at,
                  seconds_remaining=ttl, price_breakdown=booking.price_breakdown_json,
                  partner_attributed=partner is not None)
    tenant_id = ctx.tenant.id
    await ctx.session.commit()          # DB row is durable BEFORE the Redis timer starts
    try:
        await get_redis().set(hold_key(tenant_id, booking.id), "1", ex=ttl)   # expiry -> keyspace event -> release
    except Exception:  # noqa: BLE001 - the Celery sweep still releases the hold
        log.warning("redis hold key not set for %s", booking.id, exc_info=True)
    await publish(tenant_id, "unit.hold", {"unit_id": booking.unit_id, "booking_id": booking.id, "status": "ON_HOLD"})
    return out


@router.post("/confirm", response_model=ConfirmOut, summary="Confirm a hold with full or partial (deposit) payment")
async def confirm(body: ConfirmRequest, ctx: TenantContext = Depends(authorize("bookings:create"))):
    booking = await svc.confirm_payment(ctx, body)
    out = ConfirmOut(booking_id=booking.id, booking_ref=booking.booking_ref, status=booking.status,
                     total_amount=booking.total_amount, paid_amount=booking.paid_amount,
                     balance_due=q(booking.total_amount - booking.paid_amount),
                     payment_state="PAID" if booking.paid_amount >= booking.total_amount else "PARTIAL")
    tenant_id = ctx.tenant.id
    await ctx.session.commit()
    try:
        await get_redis().delete(hold_key(tenant_id, booking.id))      # stop the release timer
    except Exception:  # noqa: BLE001
        log.warning("redis hold key not deleted", exc_info=True)
    await publish(tenant_id, "unit.booked", {"unit_id": booking.unit_id, "booking_id": booking.id, "status": "BOOKED"})
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("app.workers.tasks.send_booking_confirmation", args=[str(tenant_id), str(booking.id)])
    except Exception:  # noqa: BLE001
        log.warning("could not enqueue confirmation email", exc_info=True)
    return out


@router.get("", response_model=Page[BookingOut], summary="List bookings")
async def list_bookings(status_: BookingStatus | None = Query(None, alias="status"), unit_id: UUID | None = None,
                        partner_id: UUID | None = None, pg: Pagination = Depends(),
                        ctx: TenantContext = Depends(authorize("bookings:read"))):
    stmt = select(Booking).where(Booking.tenant_id == ctx.tenant.id).order_by(Booking.created_at.desc())
    if status_:
        stmt = stmt.where(Booking.status == status_)
    if unit_id:
        stmt = stmt.where(Booking.unit_id == unit_id)
    if partner_id:
        stmt = stmt.where(Booking.partner_id == partner_id)
    return await paginate(ctx.session, stmt, pg)


@router.get("/{booking_id}", response_model=BookingOut, summary="Get booking")
async def get_booking(booking_id: UUID, ctx: TenantContext = Depends(authorize("bookings:read"))):
    return await get_or_404(ctx, Booking, booking_id, "Booking")


@router.post("/{booking_id}/cancel", response_model=BookingOut, summary="Cancel booking (reverses partner commission)")
async def cancel(booking_id: UUID, body: CancelRequest, ctx: TenantContext = Depends(authorize("bookings:manage"))):
    booking = await svc.cancel_booking(ctx, booking_id, body.reason)
    await publish(ctx.tenant.id, "unit.released", {"unit_id": booking.unit_id, "booking_id": booking.id, "status": "AVAILABLE"})
    return booking
