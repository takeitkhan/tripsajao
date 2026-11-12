import secrets
import string
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.services.limits import enforce
from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.core.security import hash_password
from app.models import Booking, BookingStatus, LedgerType, Partner, PartnerLedger
from app.schemas.common import Page, Pagination
from app.schemas.partner import (LedgerEntryOut, LedgerStatement, PartnerBookingOut, PartnerCreate, PartnerDashboard,
                                 PartnerOut, PartnerUpdate)
from app.services.ledger import ledger_totals, reserved_for_payouts
from app.services.pricing import ZERO, q

router = APIRouter(prefix="/partners", tags=["partners"])
_ALPHABET = string.ascii_letters + string.digits


def short_link(ctx: TenantContext, code: str) -> str:
    return f"https://{ctx.tenant.domain}/go/{code}"


def _out(ctx: TenantContext, p: Partner) -> PartnerOut:
    out = PartnerOut.model_validate(p)
    out.short_link = short_link(ctx, p.vanity_code)
    return out


async def _statement(ctx: TenantContext, partner_id: UUID, pg: Pagination) -> LedgerStatement:
    credit, debit, balance = await ledger_totals(ctx.session, partner_id)
    reserved = await reserved_for_payouts(ctx.session, partner_id)
    rows = (await ctx.session.execute(select(PartnerLedger).where(PartnerLedger.partner_id == partner_id)
                                      .order_by(PartnerLedger.seq.desc()).limit(pg.limit).offset(pg.offset))).scalars().all()
    return LedgerStatement(partner_id=partner_id, total_credit=credit, total_debit=debit, closing_balance=balance,
                           reserved_for_payouts=reserved, available_for_payout=q(balance - reserved),
                           entries=[LedgerEntryOut.model_validate(r) for r in rows])


# ---------------- partner portal (JWT principal = partner) ----------------
@router.get("/me/dashboard", response_model=PartnerDashboard, summary="Partner portal: sales, commission, balance")
async def my_dashboard(ctx: TenantContext = Depends(authorize("partner:self"))):
    pid = ctx.principal.partner_id
    partner = await get_or_404(ctx, Partner, pid, "Partner")
    count, gross = (await ctx.session.execute(select(func.count(), func.coalesce(func.sum(Booking.total_amount), 0)).where(
        Booking.partner_id == pid, Booking.status == BookingStatus.CONFIRMED))).one()
    credit, debit, balance = await ledger_totals(ctx.session, pid)
    paid_out = (await ctx.session.execute(select(func.coalesce(func.sum(PartnerLedger.debit), 0)).where(
        PartnerLedger.partner_id == pid, PartnerLedger.transaction_type == LedgerType.PAYOUT))).scalar_one()
    reserved = await reserved_for_payouts(ctx.session, pid)
    min_payout = Decimal(str(ctx.tenant.settings_json.get("min_payout", 1000)))
    return PartnerDashboard(confirmed_bookings=count, gross_sales=q(Decimal(gross)), commission_earned=credit,
                            paid_out=q(Decimal(paid_out)), ledger_balance=balance, reserved_for_payouts=reserved,
                            available_for_payout=q(balance - reserved), min_payout=min_payout,
                            short_link=short_link(ctx, partner.vanity_code))


@router.get("/me/ledger", response_model=LedgerStatement, summary="Partner portal: ledger statement")
async def my_ledger(pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("partner:self"))):
    return await _statement(ctx, ctx.principal.partner_id, pg)


@router.get("/me/bookings", response_model=Page[PartnerBookingOut], summary="Partner portal: attributed bookings")
async def my_bookings(pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("partner:self"))):
    stmt = select(Booking).where(Booking.partner_id == ctx.principal.partner_id).order_by(Booking.created_at.desc())
    page = await paginate(ctx.session, stmt, pg)
    page["items"] = [PartnerBookingOut(booking_ref=b.booking_ref, check_in=b.check_in, check_out=b.check_out,
                                       total_amount=b.total_amount, paid_amount=b.paid_amount,
                                       commission_amount=b.commission_amount, status=b.status.value) for b in page["items"]]
    return page


# ---------------- tenant admin ----------------
@router.post("", response_model=PartnerOut, status_code=201, summary="Create partner (+ obfuscated short link)")
async def create_partner(body: PartnerCreate, ctx: TenantContext = Depends(authorize("partners:write"))):
    await enforce(ctx, "max_partners", Partner)
    code = body.vanity_code
    for _ in range(5):
        candidate = code or "".join(secrets.choice(_ALPHABET) for _ in range(6))
        taken = (await ctx.session.execute(select(Partner.id).where(Partner.vanity_code == candidate))).first()
        # NB: RLS hides other tenants' rows, so a stale pre-check is only a hint; the global UNIQUE constraint decides.
        if not taken:
            code = candidate
            break
        if body.vanity_code:
            raise HTTPException(409, "Vanity code already taken")
    partner = Partner(tenant_id=ctx.tenant.id, name=body.name, email=body.email.lower(),
                      password_hash=hash_password(body.password), partner_type=body.partner_type,
                      commission_type=body.commission_type, commission_value=body.commission_value, vanity_code=code)
    await persist(ctx.session, partner, "Partner email or vanity code already exists")
    return _out(ctx, partner)


@router.get("", response_model=Page[PartnerOut], summary="List partners")
async def list_partners(pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("partners:read"))):
    page = await paginate(ctx.session, select(Partner).where(Partner.tenant_id == ctx.tenant.id).order_by(Partner.name), pg)
    page["items"] = [_out(ctx, p) for p in page["items"]]
    return page


@router.get("/{partner_id}", response_model=PartnerOut, summary="Get partner")
async def get_partner(partner_id: UUID, ctx: TenantContext = Depends(authorize("partners:read"))):
    return _out(ctx, await get_or_404(ctx, Partner, partner_id, "Partner"))


@router.patch("/{partner_id}", response_model=PartnerOut, summary="Update commission settings / vanity code / status")
async def update_partner(partner_id: UUID, body: PartnerUpdate, ctx: TenantContext = Depends(authorize("partners:write"))):
    """Commission changes apply to FUTURE bookings only; existing bookings keep their snapshotted commission."""
    partner = await get_or_404(ctx, Partner, partner_id, "Partner")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(partner, k, v)
    if partner.commission_type.value == "PERCENT" and partner.commission_value > 100:
        raise HTTPException(422, "percent commission cannot exceed 100")
    await persist(ctx.session, partner, "Vanity code already exists")
    return _out(ctx, partner)


@router.get("/{partner_id}/ledger", response_model=LedgerStatement, summary="Partner ledger statement (admin)")
async def partner_ledger(partner_id: UUID, pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("partners:read"))):
    await get_or_404(ctx, Partner, partner_id, "Partner")
    return await _statement(ctx, partner_id, pg)
