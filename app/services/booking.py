"""Booking orchestration: hold -> confirm (full / partial / balance) -> cancel."""
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import literal_column, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.deps import TenantContext
from app.models import Booking, BookingStatus, Partner, Unit, UnitStatus
from app.schemas.booking import ConfirmRequest, HoldRequest
from app.services.holds import assert_available, release_expired
from app.services.ledger import commission_for, sync_booking_commission
from app.services.pricing import ZERO, q, quote_for_unit

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelSale:
    """The reseller and the terms this sale is made under (copied onto the booking)."""
    tenant_id: UUID
    agreement_id: UUID
    name: str
    commission_type: str
    commission_value: Decimal

    def commission_for(self, nights: int, total: Decimal) -> Decimal:
        if self.commission_type == "FLAT":
            return q(self.commission_value * nights)
        return q(total * self.commission_value / Decimal(100))     # percent of each night's price = percent of the room total


def hold_seconds(ctx: TenantContext) -> int:
    return int(ctx.tenant.settings_json.get("hold_seconds", settings.hold_ttl_seconds))


def deposit_for(ctx: TenantContext, total: Decimal) -> Decimal:
    pct = Decimal(str(ctx.tenant.settings_json.get("deposit_percent", settings.default_deposit_percent)))
    return q(total * pct / Decimal(100))


async def verify_payment(reference: str, amount: Decimal, gateway: str) -> bool:
    """TODO(integration): verify `reference` with the real gateway (Stripe / Razorpay / SSLCommerz / bKash)
    or trust a signed webhook. Until wired, this accepts every reference - DO NOT ship to production as is."""
    return True


async def create_hold(ctx: TenantContext, req: HoldRequest, partner: Partner | None, channel: ChannelSale | None = None) -> Booking:
    s, tenant = ctx.session, ctx.tenant
    today = datetime.now(ZoneInfo(tenant.settings_json.get("timezone", "UTC"))).date()
    if req.check_in < today:
        raise HTTPException(422, "check_in is in the past")

    unit = (await s.execute(select(Unit).where(Unit.id == req.unit_id, Unit.tenant_id == tenant.id,
                                               Unit.is_active.is_(True)))).scalar_one_or_none()
    if unit is None:
        raise HTTPException(404, "Unit not found")
    if unit.status == UnitStatus.MAINTENANCE:
        raise HTTPException(409, "Unit is under maintenance")
    if req.guests > unit.capacity:
        raise HTTPException(422, f"Capacity exceeded (max {unit.capacity})")

    # Serialise all hold attempts for one property (also covers whole-boat vs cabin races).
    await s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                    {"k": f"{tenant.id}:{unit.property_id}"})
    await release_expired(s, tenant_id=tenant.id, property_id=unit.property_id)   # lazy cleanup of stale holds
    await assert_available(s, unit, req.check_in, req.check_out)

    stay = await quote_for_unit(s, tenant.id, unit.id, req.check_in, req.check_out)
    ttl = hold_seconds(ctx)
    booking = Booking(
        tenant_id=tenant.id, unit_id=unit.id, property_id=unit.property_id,
        partner_id=partner.id if partner else None,
        booking_ref="BK" + secrets.token_hex(4).upper(),
        customer_info_json=req.customer.model_dump(mode="json"),
        check_in=req.check_in, check_out=req.check_out, guests=req.guests, currency=stay.currency,
        total_amount=stay.total, paid_amount=ZERO,
        commission_amount=commission_for(partner, stay.total) if partner else ZERO,
        status=BookingStatus.HOLD,
        channel_tenant_id=channel.tenant_id if channel else None, channel_agreement_id=channel.agreement_id if channel else None,
        channel_name=channel.name if channel else None, channel_commission_type=channel.commission_type if channel else None,
        channel_commission_value=channel.commission_value if channel else None,
        channel_commission_amount=channel.commission_for(len(stay.nights), stay.total) if channel else ZERO,
        hold_expires_at=literal_column(f"clock_timestamp() + interval '{ttl} seconds'"),   # DB clock = authority
        price_breakdown_json={"nights": [{"night": n.night.isoformat(), "day_type": n.day_type,
                                          "base_price": str(n.base_price), "applied_rules": n.applied_rules,
                                          "price": str(n.price)} for n in stay.nights]},
        payments_json=[],
    )
    s.add(booking)
    try:
        await s.flush()
    except IntegrityError as exc:       # exclusion constraint: someone else won the race
        raise HTTPException(409, "Selected dates are no longer available") from exc
    await s.refresh(booking)
    return booking


async def confirm_payment(ctx: TenantContext, req: ConfirmRequest, recorded_by: str | None = None) -> Booking:
    s = ctx.session
    b = (await s.execute(select(Booking).where(Booking.id == req.booking_id, Booking.tenant_id == ctx.tenant.id)
                         .with_for_update())).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Booking not found")
    if b.status == BookingStatus.CANCELLED:
        raise HTTPException(410, "Hold expired or booking cancelled - refund any captured payment")
    if any(p.get("reference") == req.payment_reference for p in b.payments_json):
        raise HTTPException(409, "Payment reference already applied")

    remaining = q(b.total_amount - b.paid_amount)
    amount = q(req.amount)
    if remaining <= 0:
        raise HTTPException(409, "Booking is already fully paid")
    if amount > remaining:
        raise HTTPException(422, f"Amount exceeds balance due ({remaining})")
    if b.status == BookingStatus.HOLD:
        required = b.total_amount if req.payment_mode == "FULL" else deposit_for(ctx, b.total_amount)
        if amount < required:
            raise HTTPException(422, f"Minimum payment for {req.payment_mode} is {required}")
    # NB: a HOLD whose timer lapsed but has not been swept yet still owns the dates (the exclusion constraint
    # guarantees nobody else could take them), so a verified payment is honoured instead of being refunded.

    if not await verify_payment(req.payment_reference, amount, req.gateway):
        raise HTTPException(402, "Payment could not be verified")

    b.paid_amount = q(b.paid_amount + amount)
    b.status = BookingStatus.CONFIRMED
    b.hold_expires_at = None
    b.payments_json = [*b.payments_json, {"reference": req.payment_reference, "gateway": req.gateway,
                                         "amount": str(amount), "at": datetime.now(timezone.utc).isoformat(),
                                         **({"recorded_by": recorded_by} if recorded_by else {})}]
    await s.flush()
    await sync_booking_commission(s, b)
    await s.refresh(b)
    return b


async def cancel_booking(ctx: TenantContext, booking_id: UUID, reason: str) -> Booking:
    s = ctx.session
    b = (await s.execute(select(Booking).where(Booking.id == booking_id, Booking.tenant_id == ctx.tenant.id)
                         .with_for_update())).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Booking not found")
    if b.status == BookingStatus.CANCELLED:
        return b
    b.status, b.cancel_reason, b.hold_expires_at = BookingStatus.CANCELLED, reason, None
    await s.flush()
    await sync_booking_commission(s, b, cancelled=True)     # posts a reversal if commission had accrued
    await s.refresh(b)
    return b
