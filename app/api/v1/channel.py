import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import TenantContext, authorize
from app.core.redis import get_redis
from app.models import (Booking, BookingStatus, ChannelAgreement, ChannelAgreementProperty, ChannelCancellation, Property, Unit)
from app.schemas.booking import ConfirmOut, ConfirmRequest, HoldOut
from app.schemas.channel import (AgreementOut, ChannelBookingOut, ChannelBookingPage, ChannelConfirm, ChannelHold, ChannelProperty,
                                 ChannelUnit, Invite, RequestAccess, Terms)
from app.services import booking as svc
from app.services import channel as ch
from app.services.events import publish
from app.services.holds import hold_key
from app.services.pricing import q, quote_for_unit
from app.services.visual import live_status

log = logging.getLogger(__name__)
router = APIRouter(prefix="/channel", tags=["channel"])

LIVE_FOR_LIST = ("ACTIVE", "PAUSED", "INVITED")


# ------------------------------------------------------------------------------------------ agreements
@router.get("/agreements", response_model=list[AgreementOut], summary="Agreements this business is part of (as owner and as reseller)")
async def list_agreements(role: str | None = Query(None, pattern="^(OWNER|RESELLER)$"), ctx: TenantContext = Depends(authorize("channel:read"))):
    rows = (await ctx.session.execute(select(ChannelAgreement).order_by(ChannelAgreement.updated_at.desc()))).scalars().all()
    out = []
    for ag in rows:
        if role and ch.side(ctx, ag) != role:
            continue
        out.append(await ch.agreement_out(ctx, ag, None if ag.status in LIVE_FOR_LIST else []))
    return out


async def _apply_terms(ctx: TenantContext, ag: ChannelAgreement, terms: Terms) -> None:
    s = ctx.session
    ids = {g.property_id for g in terms.properties}
    found = set((await s.execute(select(Property.id).where(Property.tenant_id == ctx.tenant.id, Property.id.in_(ids), Property.is_active.is_(True)))).scalars())
    if found != ids:
        raise HTTPException(422, "One of the chosen properties was not found.")
    ag.commission_type, ag.commission_value = terms.commission_type, terms.commission_value
    if terms.note is not None:
        ag.note = terms.note
    if terms.settlement_mode is not None:
        ag.settlement_mode = terms.settlement_mode
        ag.settlement_day = terms.settlement_day if terms.settlement_day is not None else (10 if terms.settlement_mode == "MONTHLY" else 7)
    elif terms.settlement_day is not None:
        if ag.settlement_mode == "MONTHLY" and terms.settlement_day > 28:
            raise HTTPException(422, "For monthly settlement choose a day from 1 to 28")
        ag.settlement_day = terms.settlement_day
    await s.execute(delete(ChannelAgreementProperty).where(ChannelAgreementProperty.agreement_id == ag.id))
    s.add_all([ChannelAgreementProperty(agreement_id=ag.id, supplier_tenant_id=ag.supplier_tenant_id, reseller_tenant_id=ag.reseller_tenant_id,
                                        property_id=g.property_id, commission_type=g.commission_type, commission_value=g.commission_value)
               for g in terms.properties])
    await s.flush()


async def _existing(ctx: TenantContext, owner_id: UUID, reseller_id: UUID) -> ChannelAgreement | None:
    return (await ctx.session.execute(select(ChannelAgreement).where(
        ChannelAgreement.supplier_tenant_id == owner_id, ChannelAgreement.reseller_tenant_id == reseller_id))).scalar_one_or_none()


async def _reset(ctx: TenantContext, ag: ChannelAgreement) -> None:
    ag.commission_type = ag.commission_value = ag.ended_by = ag.decided_at = None
    await ctx.session.execute(delete(ChannelAgreementProperty).where(ChannelAgreementProperty.agreement_id == ag.id))


@router.post("/agreements/request", response_model=AgreementOut, status_code=201, summary="Ask a business to let you sell its rooms")
async def request_access(body: RequestAccess, ctx: TenantContext = Depends(authorize("channel:manage"))):
    await ch.rate_limit(f"channel:{ctx.tenant.id}", 20, 3600)
    owner = await ch.find_business(ctx.session, body.owner_domain)
    if owner.id == ctx.tenant.id:
        raise HTTPException(422, "You cannot sell your own rooms through a reseller agreement.")
    ag = await _existing(ctx, owner.id, ctx.tenant.id)
    if ag is not None:
        if ag.status in ("ACTIVE", "PAUSED"):
            raise HTTPException(409, f"You already sell for {owner.name}.")
        if ag.status == "REQUESTED":
            raise HTTPException(409, f"You already asked {owner.name}. Wait for their answer.")
        if ag.status == "INVITED":
            raise HTTPException(409, f"{owner.name} has already invited you. Accept the invitation instead.")
        await _reset(ctx, ag)
        ag.status, ag.initiated_by, ag.note = "REQUESTED", "RESELLER", body.note
        ag.supplier_name, ag.reseller_name = owner.name, ctx.tenant.name
    else:
        ag = ChannelAgreement(supplier_tenant_id=owner.id, reseller_tenant_id=ctx.tenant.id, supplier_name=owner.name, reseller_name=ctx.tenant.name,
                              status="REQUESTED", initiated_by="RESELLER", note=body.note)
        ctx.session.add(ag)
    try:
        await ctx.session.flush()
    except IntegrityError:
        raise HTTPException(409, "There is already an agreement with this business.")
    return await ch.agreement_out(ctx, ag)


@router.post("/agreements/invite", response_model=AgreementOut, status_code=201, summary="Invite a business to sell some of your properties")
async def invite(body: Invite, ctx: TenantContext = Depends(authorize("channel:manage"))):
    await ch.rate_limit(f"channel:{ctx.tenant.id}", 20, 3600)
    reseller = await ch.find_business(ctx.session, body.reseller_domain)
    if reseller.id == ctx.tenant.id:
        raise HTTPException(422, "You cannot invite your own business.")
    ag = await _existing(ctx, ctx.tenant.id, reseller.id)
    if ag is not None:
        if ag.status in ("ACTIVE", "PAUSED"):
            raise HTTPException(409, f"{reseller.name} already sells for you. Change their terms instead.")
        if ag.status == "INVITED":
            raise HTTPException(409, f"You already invited {reseller.name}.")
        if ag.status == "REQUESTED":
            raise HTTPException(409, f"{reseller.name} has already asked to sell for you. Accept their request instead.")
        await _reset(ctx, ag)
        ag.status, ag.initiated_by = "INVITED", "OWNER"
        ag.supplier_name, ag.reseller_name = ctx.tenant.name, reseller.name
    else:
        ag = ChannelAgreement(supplier_tenant_id=ctx.tenant.id, reseller_tenant_id=reseller.id, supplier_name=ctx.tenant.name, reseller_name=reseller.name,
                              status="INVITED", initiated_by="OWNER")
        ctx.session.add(ag)
    try:
        await ctx.session.flush()
    except IntegrityError:
        raise HTTPException(409, "There is already an agreement with this business.")
    await _apply_terms(ctx, ag, body)
    return await ch.agreement_out(ctx, ag)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/agreements/{agreement_id}/accept", response_model=AgreementOut,
             summary="Accept: the owner accepts a request (and sets the terms), or the reseller accepts an invitation")
async def accept(agreement_id: UUID, body: Terms | None = None, ctx: TenantContext = Depends(authorize("channel:manage"))):
    ag = await ch.get_agreement(ctx, agreement_id)
    me = ch.side(ctx, ag)
    if ag.status == "REQUESTED" and me == "OWNER":
        if body is None:
            raise HTTPException(422, "Choose the commission and the properties you allow.")
        await _apply_terms(ctx, ag, body)
    elif ag.status == "INVITED" and me == "RESELLER":
        pass
    else:
        raise HTTPException(409, "There is nothing for you to accept on this agreement.")
    ag.status, ag.decided_at = "ACTIVE", _now()
    await ctx.session.flush()
    return await ch.agreement_out(ctx, ag)


async def _move(ctx: TenantContext, agreement_id: UUID, allowed: tuple[str, ...], to: str, *, only: str | None = None, message: str) -> AgreementOut:
    ag = await ch.get_agreement(ctx, agreement_id, as_side=only)
    if ag.status not in allowed:
        raise HTTPException(409, message)
    ag.status, ag.decided_at = to, _now()
    if to == "ENDED":
        ag.ended_by = ch.side(ctx, ag)
    await ctx.session.flush()
    return await ch.agreement_out(ctx, ag, [] if to in ("ENDED", "DECLINED") else None)


@router.post("/agreements/{agreement_id}/decline", response_model=AgreementOut, summary="Decline a request or invitation addressed to you")
async def decline(agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    ag = await ch.get_agreement(ctx, agreement_id)
    waiting = {"REQUESTED": "OWNER", "INVITED": "RESELLER"}.get(ag.status)
    if waiting != ch.side(ctx, ag):
        raise HTTPException(409, "There is nothing for you to decline on this agreement.")
    return await _move(ctx, agreement_id, (ag.status,), "DECLINED", message="Already answered.")


@router.post("/agreements/{agreement_id}/withdraw", response_model=AgreementOut, summary="Take back your own pending request or invitation")
async def withdraw(agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    ag = await ch.get_agreement(ctx, agreement_id)
    if ag.status not in ("REQUESTED", "INVITED") or ag.initiated_by != ch.side(ctx, ag):
        raise HTTPException(409, "You have no pending request or invitation here to take back.")
    return await _move(ctx, agreement_id, (ag.status,), "ENDED", message="Already answered.")


@router.post("/agreements/{agreement_id}/pause", response_model=AgreementOut, summary="Owner: stop new bookings for now (existing bookings stay)")
async def pause(agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    return await _move(ctx, agreement_id, ("ACTIVE",), "PAUSED", only="OWNER", message="Only an active agreement can be paused.")


@router.post("/agreements/{agreement_id}/resume", response_model=AgreementOut, summary="Owner: allow new bookings again")
async def resume(agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    return await _move(ctx, agreement_id, ("PAUSED",), "ACTIVE", only="OWNER", message="Only a paused agreement can be resumed.")


@router.post("/agreements/{agreement_id}/end", response_model=AgreementOut, summary="End the agreement (either side). Existing bookings and money owed stay")
async def end(agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    return await _move(ctx, agreement_id, ("ACTIVE", "PAUSED"), "ENDED", message="Only a running agreement can be ended.")


@router.put("/agreements/{agreement_id}/terms", response_model=AgreementOut, summary="Owner: change commission and allowed properties (new bookings only)")
async def change_terms(agreement_id: UUID, body: Terms, ctx: TenantContext = Depends(authorize("channel:manage"))):
    ag = await ch.get_agreement(ctx, agreement_id, as_side="OWNER")
    if ag.status not in ("ACTIVE", "PAUSED", "INVITED"):
        raise HTTPException(409, "Terms can be changed on a running agreement or a pending invitation.")
    await _apply_terms(ctx, ag, body)
    return await ch.agreement_out(ctx, ag)


# ------------------------------------------------------------------------------------------ reseller: find rooms
async def _active_agreements(ctx: TenantContext) -> list[ChannelAgreement]:
    return list((await ctx.session.execute(select(ChannelAgreement).where(
        ChannelAgreement.reseller_tenant_id == ctx.tenant.id, ChannelAgreement.status == "ACTIVE").order_by(ChannelAgreement.supplier_name))).scalars())


@router.get("/properties", response_model=list[ChannelProperty], summary="Properties you may sell (from every active agreement)")
async def properties(ctx: TenantContext = Depends(authorize("channel:read"))):
    out = []
    for ag in await _active_agreements(ctx):
        grants = {g.property_id: g for g in await ch.grants_of(ctx.session, ag.id)}
        async with ch.owner_scope(ag.supplier_tenant_id, required=False) as oc:
            if oc is None or not grants:
                continue
            for p in (await oc.session.execute(select(Property).where(Property.tenant_id == oc.tenant.id, Property.id.in_(list(grants)),
                                                                      Property.is_active.is_(True)).order_by(Property.name))).scalars():
                kind, value = ch.terms_for(ag, grants[p.id])
                meta = p.metadata_json or {}
                out.append(ChannelProperty(agreement_id=ag.id, owner=ag.supplier_name, property_id=p.id, name=p.name, type=p.type.value, location=p.location,
                                           description=meta.get("description"), amenities=meta.get("amenities") or [], media=meta.get("media") or [],
                                           commission_type=kind, commission_value=value))
    return out


@router.get("/availability", response_model=list[ChannelUnit], summary="Free rooms of a granted property for a date range, with price and your commission")
async def availability(agreement_id: UUID, property_id: UUID, check_in: date, check_out: date, guests: int = Query(1, ge=1),
                       ctx: TenantContext = Depends(authorize("channel:read"))):
    if check_out <= check_in:
        raise HTTPException(422, "check_out must be after check_in")
    ag, grants = await ch.sellable(ctx, agreement_id)
    if property_id not in grants:
        raise HTTPException(404, "Property not found")
    sale = ch.sale_for(ag, grants[property_id])
    out = []
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        units, live = await live_status(oc.session, oc.tenant.id, property_id, check_in, check_out)
        for u in units:
            if live[u.id]["status"] != "AVAILABLE" or u.capacity < guests:
                continue
            try:
                stay = await quote_for_unit(oc.session, oc.tenant.id, u.id, check_in, check_out)
            except HTTPException:
                continue
            out.append(ChannelUnit(unit_id=u.id, unit_name=u.unit_name, unit_type=u.type.value, capacity=u.capacity, facilities=u.facilities_json,
                                   currency=stay.currency, total=stay.total, nights=len(stay.nights), your_commission=sale.commission_for(len(stay.nights), stay.total)))
    return out


# ------------------------------------------------------------------------------------------ reseller: book
@router.post("/hold", response_model=HoldOut, status_code=status.HTTP_201_CREATED, summary="Lock a room for 10 minutes while the guest pays the owner")
async def hold(body: ChannelHold, ctx: TenantContext = Depends(authorize("channel:book"))):
    ag, grants = await ch.sellable(ctx, body.agreement_id)
    if body.property_id not in grants:
        raise HTTPException(404, "Property not found")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        unit = (await oc.session.execute(select(Unit).where(Unit.id == body.unit_id, Unit.tenant_id == oc.tenant.id,
                                                            Unit.property_id == body.property_id, Unit.is_active.is_(True)))).scalar_one_or_none()
        if unit is None:
            raise HTTPException(404, "Unit not found")                  # also when the room belongs to a property the owner did not grant
        booking = await svc.create_hold(oc, body, None, ch.sale_for(ag, grants[body.property_id]))
        ttl = svc.hold_seconds(oc)
        out = HoldOut(booking_id=booking.id, booking_ref=booking.booking_ref, status=booking.status, unit_id=booking.unit_id, check_in=booking.check_in,
                      check_out=booking.check_out, nights=(booking.check_out - booking.check_in).days, currency=booking.currency,
                      total_amount=booking.total_amount, deposit_amount=svc.deposit_for(oc, booking.total_amount), hold_expires_at=booking.hold_expires_at,
                      seconds_remaining=ttl, price_breakdown=booking.price_breakdown_json, partner_attributed=False)
        owner_id, bid, uid = oc.tenant.id, booking.id, booking.unit_id
        await oc.session.commit()                                       # the row is durable BEFORE the timer starts
    try:
        await get_redis().set(hold_key(owner_id, bid), "1", ex=ttl)
    except Exception:  # noqa: BLE001 - the Celery sweep still releases it
        log.warning("redis hold key not set for %s", bid, exc_info=True)
    await publish(owner_id, "unit.hold", {"unit_id": uid, "booking_id": bid, "status": "ON_HOLD"})
    return out


async def _own_booking(oc: TenantContext, ctx: TenantContext, booking_id: UUID) -> Booking:
    b = (await oc.session.execute(select(Booking).where(Booking.id == booking_id, Booking.tenant_id == oc.tenant.id,
                                                        Booking.channel_tenant_id == ctx.tenant.id))).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Booking not found")
    return b


@router.post("/confirm", response_model=ConfirmOut, summary="Record the guest's payment to the owner and confirm the booking")
async def confirm(body: ChannelConfirm, ctx: TenantContext = Depends(authorize("channel:book"))):
    ag = await ch.get_agreement(ctx, body.agreement_id, as_side="RESELLER")
    if ag.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(409, "This agreement has ended.")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        await _own_booking(oc, ctx, body.booking_id)
        b = await svc.confirm_payment(oc, ConfirmRequest(**body.model_dump(exclude={"agreement_id"})), recorded_by=f"reseller:{ctx.tenant.name}")
        out = ConfirmOut(booking_id=b.id, booking_ref=b.booking_ref, status=b.status, total_amount=b.total_amount, paid_amount=b.paid_amount,
                         balance_due=q(b.total_amount - b.paid_amount), payment_state="PAID" if b.paid_amount >= b.total_amount else "PARTIAL")
        owner_id, bid, uid = oc.tenant.id, b.id, b.unit_id
        await oc.session.commit()
    try:
        await get_redis().delete(hold_key(owner_id, bid))
    except Exception:  # noqa: BLE001
        log.warning("redis hold key not deleted", exc_info=True)
    await publish(owner_id, "unit.booked", {"unit_id": uid, "booking_id": bid, "status": "BOOKED"})
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("app.workers.tasks.send_booking_confirmation", args=[str(owner_id), str(bid)])
    except Exception:  # noqa: BLE001
        log.warning("could not enqueue confirmation email", exc_info=True)
    return out


@router.post("/bookings/{booking_id}/release", summary="Give up a hold that is not paid yet")
async def release(booking_id: UUID, agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:book"))):
    ag = await ch.get_agreement(ctx, agreement_id, as_side="RESELLER")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        b = await _own_booking(oc, ctx, booking_id)
        if b.status != BookingStatus.HOLD:
            raise HTTPException(409, "Only a hold that is not paid yet can be given up. To cancel a paid booking, ask the owner.")
        await svc.cancel_booking(oc, b.id, "RELEASED_BY_RESELLER")
        owner_id, uid = oc.tenant.id, b.unit_id
        await oc.session.commit()
    try:
        await get_redis().delete(hold_key(owner_id, booking_id))
    except Exception:  # noqa: BLE001
        pass
    await publish(owner_id, "unit.released", {"unit_id": uid, "booking_id": booking_id, "status": "AVAILABLE"})
    return {"released": True}


@router.get("/bookings", response_model=ChannelBookingPage, summary="Bookings you made for other businesses (guest details are yours alone)")
async def my_bookings(status_: str | None = Query(None, alias="status", pattern="^(HOLD|CONFIRMED|CANCELLED)$"), limit: int = Query(25, ge=1, le=100),
                      offset: int = Query(0, ge=0), ctx: TenantContext = Depends(authorize("channel:read"))):
    ags = (await ctx.session.execute(select(ChannelAgreement).where(ChannelAgreement.reseller_tenant_id == ctx.tenant.id,
                                                                    ChannelAgreement.status.in_(("ACTIVE", "PAUSED", "ENDED"))))).scalars().all()
    rows, total, away = [], 0, []
    now = datetime.now(timezone.utc)
    for ag in ags:
        async with ch.owner_scope(ag.supplier_tenant_id, required=False) as oc:
            if oc is None:
                away.append(ag.supplier_name)
                continue
            base = select(Booking).where(Booking.tenant_id == oc.tenant.id, Booking.channel_tenant_id == ctx.tenant.id)
            if status_:
                base = base.where(Booking.status == BookingStatus(status_))
            total += (await oc.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
            found = (await oc.session.execute(base.order_by(Booking.created_at.desc()).limit(offset + limit))).scalars().all()
            unit_names = dict((await oc.session.execute(select(Unit.id, Unit.unit_name).where(Unit.tenant_id == oc.tenant.id,
                                                                                              Unit.id.in_([b.unit_id for b in found] or [UUID(int=0)])))).all())
            prop_names = dict((await oc.session.execute(select(Property.id, Property.name).where(Property.tenant_id == oc.tenant.id,
                                                                                                 Property.id.in_([b.property_id for b in found] or [UUID(int=0)])))).all())
            latest: dict = {}
            for c in (await oc.session.execute(select(ChannelCancellation).where(
                    ChannelCancellation.tenant_id == oc.tenant.id, ChannelCancellation.reseller_tenant_id == ctx.tenant.id,
                    ChannelCancellation.booking_id.in_([b.id for b in found] or [UUID(int=0)])).order_by(ChannelCancellation.created_at))).scalars():
                latest[c.booking_id] = {"id": str(c.id), "status": c.status, "suggested_refund": str(c.suggested_refund),
                                        "refund_amount": None if c.refund_amount is None else str(c.refund_amount), "decision_note": c.decision_note}
            for b in found:
                expired = b.status == BookingStatus.HOLD and b.hold_expires_at is not None and b.hold_expires_at < now
                rows.append(ChannelBookingOut(
                    id=b.id, booking_ref=b.booking_ref, agreement_id=b.channel_agreement_id, owner=ag.supplier_name, property=prop_names.get(b.property_id, ""),
                    unit=unit_names.get(b.unit_id, ""), customer=b.customer_info_json, check_in=b.check_in, check_out=b.check_out,
                    nights=(b.check_out - b.check_in).days, guests=b.guests, currency=b.currency, total_amount=b.total_amount, paid_amount=b.paid_amount,
                    balance_due=q(b.total_amount - b.paid_amount), your_commission=b.channel_commission_amount, commission_type=b.channel_commission_type,
                    commission_value=b.channel_commission_value, status="EXPIRED" if expired else b.status.value, hold_expires_at=b.hold_expires_at,
                    cancel_reason=b.cancel_reason, cancellation=latest.get(b.id), created_at=b.created_at))
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return ChannelBookingPage(items=rows[offset:offset + limit], total=total, limit=limit, offset=offset, unavailable=away)
