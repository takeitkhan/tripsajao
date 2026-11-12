"""Cancellation and refund for bookings sold by a reseller.
The reseller asks, the system works out the refund from the owner's rules, and the owner confirms or declines.
The guest's money is with the owner, so the owner refunds the guest directly."""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import TenantContext, authorize
from app.models import Booking, BookingStatus, ChannelAgreement, ChannelCancellation, Property
from app.schemas.channel import (CancelDecision, CancelDecline, CancelQuote, CancelRequest, CancellationOut, CancellationPolicy, RefundRule)
from app.services import booking as svc
from app.services import cancellation as cx
from app.services import channel as ch
from app.services.events import publish
from app.services.pricing import q

log = logging.getLogger(__name__)
router = APIRouter(prefix="/channel", tags=["channel"])


# ------------------------------------------------------------------------------------------ the owner's refund rules
@router.get("/cancellation-policy", response_model=CancellationPolicy, summary="The refund rules for bookings sold by resellers")
async def get_policy(ctx: TenantContext = Depends(authorize("channel:read"))):
    rules, default = cx.rules_of(ctx.tenant)
    return CancellationPolicy(rules=[RefundRule(**r) for r in rules], is_default=default)


@router.put("/cancellation-policy", response_model=CancellationPolicy, summary="Set the refund rules (owner)")
async def set_policy(body: CancellationPolicy, ctx: TenantContext = Depends(authorize("channel:manage"))):
    rules = sorted(({"days_before": r.days_before, "refund_percent": float(r.refund_percent)} for r in body.rules), key=lambda r: -r["days_before"])
    ctx.tenant.settings_json = {**ctx.tenant.settings_json, "cancellation_policy": rules}            # reassign -> dirty
    return CancellationPolicy(rules=[RefundRule(**r) for r in rules], is_default=False)


# ------------------------------------------------------------------------------------------ reseller: ask
async def _booking(oc: TenantContext, booking_id: UUID, reseller_id: UUID, *, lock: bool = False) -> Booking:
    stmt = select(Booking).where(Booking.id == booking_id, Booking.tenant_id == oc.tenant.id, Booking.channel_tenant_id == reseller_id)
    b = (await oc.session.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Booking not found")
    return b


def _why_not(b: Booking, tenant) -> str | None:
    if b.status == BookingStatus.CANCELLED:
        return "This booking is already cancelled."
    if b.status != BookingStatus.CONFIRMED:
        return "Only a confirmed booking can be cancelled this way. An unpaid hold can simply be given up."
    if (b.check_in - cx.today_for(tenant)).days < 0:
        return "The stay has already started."
    return None


@router.get("/bookings/{booking_id}/cancel-quote", response_model=CancelQuote, summary="What the guest would get back if this booking were cancelled today")
async def cancel_quote(booking_id: UUID, agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:read"))):
    ag = await ch.get_agreement(ctx, agreement_id, as_side="RESELLER")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        b = await _booking(oc, booking_id, ctx.tenant.id)
        days, pct, refund = cx.refund_for(oc.tenant, b.check_in, b.paid_amount)
        why = _why_not(b, oc.tenant)
        if why is None and (await oc.session.execute(select(ChannelCancellation.id).where(ChannelCancellation.booking_id == b.id, ChannelCancellation.status == "REQUESTED"))).first():
            why = "A cancellation request for this booking is already waiting for the owner."
        return CancelQuote(booking_id=b.id, booking_ref=b.booking_ref, status=b.status.value, check_in=b.check_in, currency=b.currency, paid_amount=b.paid_amount,
                           days_before=days, refund_percent=pct, refund_amount=refund, rule_text=cx.rule_text(pct, days), can_request=why is None, why_not=why)


@router.post("/bookings/{booking_id}/cancel-request", response_model=CancellationOut, status_code=201,
             summary="Ask the owner to cancel a confirmed booking you sold. The owner decides the refund")
async def cancel_request(booking_id: UUID, body: CancelRequest, ctx: TenantContext = Depends(authorize("channel:book"))):
    ag = await ch.get_agreement(ctx, body.agreement_id, as_side="RESELLER")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        b = await _booking(oc, booking_id, ctx.tenant.id, lock=True)
        why = _why_not(b, oc.tenant)
        if why:
            raise HTTPException(409, why)
        days, pct, refund = cx.refund_for(oc.tenant, b.check_in, b.paid_amount)
        row = ChannelCancellation(tenant_id=oc.tenant.id, booking_id=b.id, booking_ref=b.booking_ref, agreement_id=ag.id, reseller_tenant_id=ctx.tenant.id,
                                  reseller_name=ag.reseller_name, reason=body.reason.strip(), currency=b.currency, paid_amount=b.paid_amount, days_before=days,
                                  policy_percent=pct, suggested_refund=refund)
        oc.session.add(row)
        try:
            await oc.session.flush()
        except IntegrityError:
            raise HTTPException(409, "A cancellation request for this booking is already waiting for the owner.")
        await oc.session.refresh(row)
        return await _out(oc, row, "RESELLER", ag.supplier_name)


@router.post("/cancellations/{cancellation_id}/withdraw", response_model=CancellationOut, summary="Reseller: take the request back before the owner decides")
async def withdraw(cancellation_id: UUID, agreement_id: UUID, ctx: TenantContext = Depends(authorize("channel:book"))):
    ag = await ch.get_agreement(ctx, agreement_id, as_side="RESELLER")
    async with ch.owner_scope(ag.supplier_tenant_id) as oc:
        row = await _row(oc, cancellation_id, reseller_id=ctx.tenant.id)
        if row.status != "REQUESTED":
            raise HTTPException(409, "The owner has already decided on this request.")
        row.status = "WITHDRAWN"
        await oc.session.flush()
        await oc.session.refresh(row)
        return await _out(oc, row, "RESELLER", ag.supplier_name)


# ------------------------------------------------------------------------------------------ both sides: list
async def _row(oc: TenantContext, cancellation_id: UUID, *, reseller_id: UUID | None = None) -> ChannelCancellation:
    stmt = select(ChannelCancellation).where(ChannelCancellation.id == cancellation_id, ChannelCancellation.tenant_id == oc.tenant.id).with_for_update()
    if reseller_id:
        stmt = stmt.where(ChannelCancellation.reseller_tenant_id == reseller_id)
    row = (await oc.session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Cancellation request not found")
    return row


async def _out(oc: TenantContext, c: ChannelCancellation, role: str, counterpart: str) -> CancellationOut:
    b = (await oc.session.execute(select(Booking).where(Booking.id == c.booking_id, Booking.tenant_id == oc.tenant.id))).scalar_one()
    prop = (await oc.session.execute(select(Property.name).where(Property.tenant_id == oc.tenant.id, Property.id == b.property_id))).scalar_one_or_none() or ""
    return CancellationOut(id=c.id, booking_id=c.booking_id, booking_ref=c.booking_ref, agreement_id=c.agreement_id, role=role, counterpart=counterpart, property=prop,
                           guest=str((b.customer_info_json or {}).get("name", "")), check_in=b.check_in, check_out=b.check_out, currency=c.currency, total_amount=b.total_amount,
                           paid_amount=c.paid_amount, days_before=c.days_before, refund_percent=c.policy_percent, suggested_refund=c.suggested_refund,
                           refund_amount=c.refund_amount, status=c.status, reason=c.reason, decision_note=c.decision_note, created_at=c.created_at, decided_at=c.decided_at)


@router.get("/cancellations", response_model=list[CancellationOut], summary="Cancellation requests (as owner and as reseller)")
async def list_cancellations(role: str | None = Query(None, pattern="^(OWNER|RESELLER)$"), status_: str | None = Query(None, alias="status", pattern="^(REQUESTED|CONFIRMED|DECLINED|WITHDRAWN)$"),
                             ctx: TenantContext = Depends(authorize("channel:read"))):
    out: list[CancellationOut] = []
    if role in (None, "OWNER"):
        stmt = select(ChannelCancellation).where(ChannelCancellation.tenant_id == ctx.tenant.id).order_by(ChannelCancellation.created_at.desc()).limit(100)
        if status_:
            stmt = stmt.where(ChannelCancellation.status == status_)
        for c in (await ctx.session.execute(stmt)).scalars():
            out.append(await _out(ctx, c, "OWNER", c.reseller_name))
    if role in (None, "RESELLER"):
        ags = (await ctx.session.execute(select(ChannelAgreement).where(ChannelAgreement.reseller_tenant_id == ctx.tenant.id))).scalars().all()
        for ag in ags:
            async with ch.owner_scope(ag.supplier_tenant_id, required=False) as oc:
                if oc is None:
                    continue
                stmt = select(ChannelCancellation).where(ChannelCancellation.tenant_id == oc.tenant.id, ChannelCancellation.reseller_tenant_id == ctx.tenant.id) \
                    .order_by(ChannelCancellation.created_at.desc()).limit(100)
                if status_:
                    stmt = stmt.where(ChannelCancellation.status == status_)
                for c in (await oc.session.execute(stmt)).scalars():
                    out.append(await _out(oc, c, "RESELLER", ag.supplier_name))
    out.sort(key=lambda c: c.created_at, reverse=True)
    return out


# ------------------------------------------------------------------------------------------ owner: decide
@router.post("/cancellations/{cancellation_id}/confirm", response_model=CancellationOut, summary="Owner: cancel the booking and agree the refund")
async def confirm(cancellation_id: UUID, body: CancelDecision, ctx: TenantContext = Depends(authorize("channel:manage"))):
    row = await _row(ctx, cancellation_id)
    if row.status != "REQUESTED":
        raise HTTPException(409, "This request was already decided." if row.status in ("CONFIRMED", "DECLINED") else "The reseller took this request back.")
    refund = q(body.refund_amount) if body.refund_amount is not None else row.suggested_refund
    b = (await ctx.session.execute(select(Booking).where(Booking.id == row.booking_id, Booking.tenant_id == ctx.tenant.id).with_for_update())).scalar_one()
    if b.status != BookingStatus.CONFIRMED:
        raise HTTPException(409, "This booking is no longer confirmed.")
    if refund > b.paid_amount:
        raise HTTPException(422, "The refund cannot be more than the guest has paid.")
    await svc.cancel_booking(ctx, b.id, f"Cancelled at the request of {row.reseller_name}")
    row.status, row.refund_amount, row.decision_note, row.decided_at = "CONFIRMED", refund, (body.note or "").strip() or None, datetime.now(timezone.utc)
    await ctx.session.flush()
    await ctx.session.refresh(row)
    out = await _out(ctx, row, "OWNER", row.reseller_name)
    await publish(ctx.tenant.id, "unit.released", {"unit_id": b.unit_id, "booking_id": b.id, "status": "AVAILABLE"})
    return out


@router.post("/cancellations/{cancellation_id}/decline", response_model=CancellationOut, summary="Owner: keep the booking")
async def decline(cancellation_id: UUID, body: CancelDecline, ctx: TenantContext = Depends(authorize("channel:manage"))):
    row = await _row(ctx, cancellation_id)
    if row.status != "REQUESTED":
        raise HTTPException(409, "This request was already decided." if row.status in ("CONFIRMED", "DECLINED") else "The reseller took this request back.")
    row.status, row.decision_note, row.decided_at = "DECLINED", body.note.strip(), datetime.now(timezone.utc)
    await ctx.session.flush()
    await ctx.session.refresh(row)
    return await _out(ctx, row, "OWNER", row.reseller_name)
