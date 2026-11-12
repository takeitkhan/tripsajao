import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select

from app.core.deps import TenantContext, authorize, get_or_404, paginate
from app.models import EventBooking, MediaKind, Partner, TourEvent
from app.schemas.common import Page, Pagination
from app.schemas.event_booking import (EventBookingCancel, EventBookingOut, EventBookingPublic, EventHoldOut, EventHoldRequest,
                                       EventPaymentIn, PaymentDecision)
from app.services import event_booking as svc
from app.services import media as media_svc
from app.services.attribution import resolve_partner
from app.services.pricing import q

router = APIRouter(tags=["event_bookings"])
TOKEN = Header(None, alias="X-Booking-Token", description="The secret returned when the seats were held")
MAX_PROOFS = 5


def _public(b: EventBooking, ev: TourEvent) -> EventBookingPublic:
    return EventBookingPublic(booking_ref=b.booking_ref, status=b.status, event_id=b.event_id, event_title=ev.title, seats=b.seats,
                              total_amount=b.total_amount, paid_amount=b.paid_amount, balance_due=q(b.total_amount - b.paid_amount),
                              currency=b.currency, hold_expires_at=b.hold_expires_at if b.status == "HOLD" else None,
                              payment_methods=list(ev.payment_methods or []), proofs=len(b.proofs_json),
                              payments=[{k: v for k, v in p.items() if k != "proofs"} | {"proofs": len(p.get("proofs", []))} for p in b.payments_json])


def _guest_view(ev_b: tuple[EventBooking, TourEvent]) -> EventBookingPublic:
    return _public(*ev_b)


async def _event_of(ctx: TenantContext, b: EventBooking) -> TourEvent:
    return await get_or_404(ctx, TourEvent, b.event_id, "Event")


# ------------------------------------------------------------------ website side (API key + secret, scope events:book)
@router.post("/events/{event_id}/hold", response_model=EventHoldOut, status_code=status.HTTP_201_CREATED, tags=["event_bookings"],
             summary="Step 1: hold seats for 10 minutes (customer details are required; partner is attributed from the cookie)")
async def hold(event_id: UUID, body: EventHoldRequest, request: Request, ctx: TenantContext = Depends(authorize("events:book"))):
    partner = await resolve_partner(ctx.session, ctx.tenant.id, request)
    b, token, ev = await svc.create_hold(ctx, event_id, body.seats, body.customer.model_dump(mode="json"), partner)
    ttl = svc.hold_seconds(ctx)
    return EventHoldOut(booking_ref=b.booking_ref, token=token, status=b.status, event_id=ev.id, seats=b.seats, unit_price=b.unit_price,
                        total_amount=b.total_amount, currency=b.currency, hold_expires_at=b.hold_expires_at, seconds_remaining=ttl,
                        payment_methods=list(ev.payment_methods or []), partner_attributed=partner is not None)


@router.get("/event-bookings/status/{ref}", response_model=EventBookingPublic, summary="Show one booking to the customer (needs the booking token)")
async def guest_status(ref: str, token: str | None = TOKEN, ctx: TenantContext = Depends(authorize("events:book"))):
    b = await svc.get_for_guest(ctx, ref, token or "")
    if b.status == "HOLD" and b.hold_expires_at and b.hold_expires_at <= datetime.now(timezone.utc):
        b.status, b.hold_expires_at = "EXPIRED", None
    return _public(b, await _event_of(ctx, b))


@router.post("/event-bookings/status/{ref}/proof", status_code=201, summary="Step 2: upload a payment screenshot (JPG/PNG/WEBP, multipart field `file`)")
async def upload_proof(ref: str, file: UploadFile = File(...), token: str | None = TOKEN, ctx: TenantContext = Depends(authorize("events:book"))):
    b = await svc.get_for_guest(ctx, ref, token or "", lock=True)
    if b.status not in ("HOLD", "CONFIRMED", "PAYMENT_SUBMITTED"):
        raise HTTPException(409, "This booking is closed")
    if b.status == "HOLD" and b.hold_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(410, "The 10 minutes are over and the seats were released. Please book again")
    if len(b.proofs_json) + sum(len(p.get("proofs", [])) for p in b.payments_json) >= MAX_PROOFS * 2:
        raise HTTPException(429, "Too many screenshots for this booking")
    asset = await media_svc.store_upload(ctx.session, ctx.tenant, None, file, f"Payment proof {b.booking_ref}", None, ["payment-proof"])
    if asset.kind != MediaKind.IMAGE:
        media_svc.remove_files(asset)
        await ctx.session.delete(asset)
        raise HTTPException(422, "Please upload a photo or screenshot")
    url = media_svc.describe(asset)["url"]
    b.proofs_json = [*b.proofs_json, url]
    return {"url": url, "proofs": len(b.proofs_json)}


@router.post("/event-bookings/status/{ref}/payment", response_model=EventBookingPublic,
             summary="Step 3: tell us how you paid (needs at least one uploaded screenshot); the business then checks the money")
async def submit_payment(ref: str, body: EventPaymentIn, token: str | None = TOKEN, ctx: TenantContext = Depends(authorize("events:book"))):
    b = await svc.get_for_guest(ctx, ref, token or "", lock=True)
    ev = await _event_of(ctx, b)
    now = datetime.now(timezone.utc)
    if b.status == "HOLD" and b.hold_expires_at <= now:
        b.status, b.hold_expires_at = "EXPIRED", None
        raise HTTPException(410, "The 10 minutes are over and the seats were released. Please book again")
    if b.status not in ("HOLD", "CONFIRMED"):
        raise HTTPException(409, "A payment is already waiting to be checked" if b.status == "PAYMENT_SUBMITTED" else "This booking is closed")
    if not b.proofs_json:
        raise HTTPException(422, "Upload a screenshot of the payment first")
    if ev.payment_methods and body.method.strip().lower() not in [m.lower() for m in ev.payment_methods]:
        raise HTTPException(422, f"Choose one of: {', '.join(ev.payment_methods)}")
    remaining = q(b.total_amount - b.paid_amount)
    if remaining <= 0:
        raise HTTPException(409, "This booking is already fully paid")
    if q(body.amount) > remaining:
        raise HTTPException(422, f"The amount is more than what is due ({remaining})")
    pay = {"id": uuid.uuid4().hex[:12], "method": body.method.strip(), "amount": str(q(body.amount)), "trx_id": body.trx_id, "sender": body.sender,
           "note": body.note, "proofs": list(b.proofs_json), "status": "SUBMITTED", "submitted_at": now.isoformat()}
    b.payments_json, b.proofs_json = [*b.payments_json, pay], []
    if b.status == "HOLD":
        b.status, b.hold_expires_at = "PAYMENT_SUBMITTED", None           # seats stay reserved until the business decides
    return _public(b, ev)


# ------------------------------------------------------------------ business side
async def _out(ctx: TenantContext, rows: list[EventBooking]) -> list[EventBookingOut]:
    ev = {e.id: e for e in (await ctx.session.execute(select(TourEvent).where(TourEvent.id.in_({b.event_id for b in rows})))).scalars()} if rows else {}
    pn = {p.id: p.name for p in (await ctx.session.execute(select(Partner).where(Partner.id.in_({b.partner_id for b in rows if b.partner_id})))).scalars()} if rows else {}
    out = []
    for b in rows:
        o = EventBookingOut.model_validate(b)
        e = ev.get(b.event_id)
        o.event_title, o.event_starts_on = (e.title, e.starts_on) if e else (None, None)
        o.partner_name = pn.get(b.partner_id)
        out.append(o)
    return out


@router.get("/event-bookings", response_model=Page[EventBookingOut], summary="List event bookings")
async def list_bookings(status_: str | None = Query(None, alias="status", pattern="^(HOLD|PAYMENT_SUBMITTED|CONFIRMED|CANCELLED|EXPIRED)$"),
                        event_id: UUID | None = None, q_: str | None = Query(None, alias="q", max_length=100), pg: Pagination = Depends(),
                        ctx: TenantContext = Depends(authorize("event_bookings:read"))):
    await svc.expire_stale(ctx.session, ctx.tenant.id)
    stmt = select(EventBooking).where(EventBooking.tenant_id == ctx.tenant.id).order_by(EventBooking.created_at.desc())
    if status_:
        stmt = stmt.where(EventBooking.status == status_)
    if event_id:
        stmt = stmt.where(EventBooking.event_id == event_id)
    if q_:
        like = f"%{q_.strip().lower()}%"
        stmt = stmt.where(func.lower(EventBooking.booking_ref + ' ' + func.coalesce(EventBooking.customer_info_json['name'].astext, '') + ' ' +
                                     func.coalesce(EventBooking.customer_info_json['phone'].astext, '') + ' ' +
                                     func.coalesce(EventBooking.customer_info_json['email'].astext, '')).like(like))
    page = await paginate(ctx.session, stmt, pg)
    page["items"] = await _out(ctx, list(page["items"]))
    return page


@router.get("/event-bookings/{booking_id}", response_model=EventBookingOut, summary="One event booking with its payments and screenshots")
async def one(booking_id: UUID, ctx: TenantContext = Depends(authorize("event_bookings:read"))):
    b = await get_or_404(ctx, EventBooking, booking_id, "Booking")
    return (await _out(ctx, [b]))[0]


async def _locked(ctx: TenantContext, booking_id: UUID) -> EventBooking:
    b = (await ctx.session.execute(select(EventBooking).where(EventBooking.id == booking_id, EventBooking.tenant_id == ctx.tenant.id)
                                   .with_for_update())).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Booking not found")
    return b


def _payment(b: EventBooking, pid: str) -> dict:
    p = next((x for x in b.payments_json if x.get("id") == pid), None)
    if p is None:
        raise HTTPException(404, "Payment not found")
    if p["status"] != "SUBMITTED":
        raise HTTPException(409, f"This payment was already {p['status'].lower()}")
    return p


def _replace(b: EventBooking, p: dict) -> None:
    b.payments_json = [p if x.get("id") == p["id"] else x for x in b.payments_json]     # new list so the change is saved


@router.post("/event-bookings/{booking_id}/payments/{payment_id}/verify", response_model=EventBookingOut,
             summary="The money arrived: confirm the booking (credits the partner's commission)")
async def verify(booking_id: UUID, payment_id: str, body: PaymentDecision, ctx: TenantContext = Depends(authorize("event_bookings:manage"))):
    b = await _locked(ctx, booking_id)
    if b.status == "CANCELLED":
        raise HTTPException(409, "This booking was cancelled")
    p = _payment(b, payment_id)
    amount = q(body.amount if body.amount is not None else Decimal(p["amount"]))
    if amount > q(b.total_amount - b.paid_amount):
        raise HTTPException(422, f"The amount is more than what is due ({q(b.total_amount - b.paid_amount)})")
    _replace(b, {**p, "status": "VERIFIED", "verified_amount": str(amount), "decided_at": datetime.now(timezone.utc).isoformat(),
                 "decided_by": str(ctx.principal.user_id) if ctx.principal.user_id else None})
    b.paid_amount, b.status, b.hold_expires_at = q(b.paid_amount + amount), "CONFIRMED", None
    await ctx.session.flush()
    await svc.sync_event_commission(ctx.session, b)
    await ctx.session.refresh(b)
    return (await _out(ctx, [b]))[0]


@router.post("/event-bookings/{booking_id}/payments/{payment_id}/reject", response_model=EventBookingOut,
             summary="The payment is wrong or missing: reject it (the customer gets 10 minutes to send it again)")
async def reject(booking_id: UUID, payment_id: str, body: PaymentDecision, ctx: TenantContext = Depends(authorize("event_bookings:manage"))):
    b = await _locked(ctx, booking_id)
    if b.status == "CANCELLED":
        raise HTTPException(409, "This booking was cancelled")
    p = _payment(b, payment_id)
    _replace(b, {**p, "status": "REJECTED", "reason": body.reason, "decided_at": datetime.now(timezone.utc).isoformat()})
    if b.status == "PAYMENT_SUBMITTED":
        b.status = "HOLD"
        b.hold_expires_at = func.clock_timestamp() + __import__("datetime").timedelta(seconds=svc.hold_seconds(ctx))
    await ctx.session.flush()
    await ctx.session.refresh(b)
    return (await _out(ctx, [b]))[0]


@router.post("/event-bookings/{booking_id}/cancel", response_model=EventBookingOut, summary="Cancel a booking, free its seats and reverse the partner's commission")
async def cancel(booking_id: UUID, body: EventBookingCancel, ctx: TenantContext = Depends(authorize("event_bookings:manage"))):
    b = await _locked(ctx, booking_id)
    if b.status != "CANCELLED":
        b.status, b.cancel_reason, b.hold_expires_at = "CANCELLED", body.reason, None
        await ctx.session.flush()
        await svc.sync_event_commission(ctx.session, b, cancelled=True)
        await ctx.session.refresh(b)
    return (await _out(ctx, [b]))[0]
