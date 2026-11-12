"""Reseller commissions: what is owed, statements, and settlement between the two businesses."""
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import TenantContext, authorize
from app.models import Booking, BookingStatus, ChannelAgreement, ChannelLedger, ChannelSettlement, ChannelSettlementItem
from app.schemas.channel import Dispute, MarkPaid, MoneyRow, StatementLine, StatementOut, SummaryOut
from app.services import channel as ch
from app.services import settlement as st

log = logging.getLogger(__name__)
router = APIRouter(prefix="/channel", tags=["channel"])
ZERO = Decimal(0)


async def _refresh(ctx: TenantContext) -> None:
    """Bring this business's commission book up to date (also done daily by the background worker)."""
    await st.refresh_owner(ctx.session, ctx.tenant.id)
    owners = {a.supplier_tenant_id for a in (await ctx.session.execute(select(ChannelAgreement).where(ChannelAgreement.reseller_tenant_id == ctx.tenant.id))).scalars()}
    for owner_id in owners:
        async with ch.owner_scope(owner_id, required=False) as oc:
            if oc is not None:
                await st.refresh_owner(oc.session, owner_id)


def _out(ctx: TenantContext, s: ChannelSettlement, lines: list[StatementLine] | None = None) -> StatementOut:
    me = "OWNER" if s.supplier_tenant_id == ctx.tenant.id else "RESELLER"
    days = st.overdue_days(s)
    return StatementOut(id=s.id, code=str(s.id)[:8].upper(), agreement_id=s.agreement_id, role=me,
                        counterpart=s.reseller_name if me == "OWNER" else s.supplier_name, mode=s.mode, period_start=s.period_start,
                        period_end=s.period_end, amount=s.amount, currency=s.currency, due_date=s.due_date, status=s.status,
                        overdue=days > 0, days_overdue=days, paid_on=s.paid_on, paid_reference=s.paid_reference, paid_note=s.paid_note,
                        paid_at=s.paid_at, confirmed_at=s.confirmed_at, dispute_reason=s.dispute_reason, disputed_at=s.disputed_at,
                        created_at=s.created_at, lines=lines)


async def _statement(ctx: TenantContext, statement_id: UUID, *, as_side: str | None = None) -> ChannelSettlement:
    s = await ctx.session.get(ChannelSettlement, statement_id)         # row level security: only the two businesses
    if s is None or ctx.tenant.id not in (s.supplier_tenant_id, s.reseller_tenant_id):
        raise HTTPException(404, "Statement not found")
    if as_side == "OWNER" and s.supplier_tenant_id != ctx.tenant.id:
        raise HTTPException(403, "Only the business that owes the commission can do that.")
    if as_side == "RESELLER" and s.reseller_tenant_id != ctx.tenant.id:
        raise HTTPException(403, "Only the business that is owed the commission can do that.")
    return s


@router.get("/statements", response_model=list[StatementOut], summary="Commission statements (as owner and as reseller)")
async def list_statements(role: str | None = Query(None, pattern="^(OWNER|RESELLER)$"), status_: str | None = Query(None, alias="status", pattern="^(DUE|PAID|CONFIRMED|DISPUTED)$"),
                          limit: int = Query(100, ge=1, le=200), ctx: TenantContext = Depends(authorize("channel:read"))):
    await _refresh(ctx)
    q = select(ChannelSettlement).order_by(ChannelSettlement.due_date.desc(), ChannelSettlement.created_at.desc()).limit(limit)
    if status_:
        q = q.where(ChannelSettlement.status == status_)
    if role == "OWNER":
        q = q.where(ChannelSettlement.supplier_tenant_id == ctx.tenant.id)
    elif role == "RESELLER":
        q = q.where(ChannelSettlement.reseller_tenant_id == ctx.tenant.id)
    return [_out(ctx, s) for s in (await ctx.session.execute(q)).scalars()]


@router.get("/statements/{statement_id}", response_model=StatementOut, summary="One statement with every booking on it")
async def get_statement(statement_id: UUID, ctx: TenantContext = Depends(authorize("channel:read"))):
    s = await _statement(ctx, statement_id)
    rows = (await ctx.session.execute(select(ChannelLedger).join(ChannelSettlementItem, ChannelSettlementItem.ledger_id == ChannelLedger.id)
                                      .where(ChannelSettlementItem.settlement_id == s.id).order_by(ChannelLedger.check_out, ChannelLedger.booking_ref))).scalars()
    lines = [StatementLine(booking_ref=r.booking_ref, property_name=r.property_name, guest_name=r.guest_name, check_in=r.check_in, check_out=r.check_out,
                           kind="COMMISSION" if r.entry_type == "ACCRUAL" else "REFUND_OF_COMMISSION", amount=r.amount) for r in rows]
    return _out(ctx, s, lines)


@router.post("/statements/{statement_id}/mark-paid", response_model=StatementOut, summary="Owner: say the commission has been paid (also after a dispute)")
async def mark_paid(statement_id: UUID, body: MarkPaid, ctx: TenantContext = Depends(authorize("channel:manage"))):
    s = await _statement(ctx, statement_id, as_side="OWNER")
    if s.status not in ("DUE", "DISPUTED"):
        raise HTTPException(409, "This statement is already marked as paid." if s.status == "PAID" else "This statement is already settled.")
    s.status, s.paid_reference, s.paid_note = "PAID", body.reference.strip(), (body.note or "").strip() or None
    s.paid_on, s.paid_at = body.paid_on or date.today(), datetime.now(timezone.utc)
    s.dispute_reason = s.disputed_at = None
    await ctx.session.flush()
    await ctx.session.refresh(s)
    return _out(ctx, s)


@router.post("/statements/{statement_id}/confirm", response_model=StatementOut, summary="Reseller: confirm the money arrived. This settles the statement")
async def confirm_received(statement_id: UUID, ctx: TenantContext = Depends(authorize("channel:manage"))):
    s = await _statement(ctx, statement_id, as_side="RESELLER")
    if s.status != "PAID":
        raise HTTPException(409, "The owner has not marked this statement as paid yet." if s.status in ("DUE", "DISPUTED") else "This statement is already settled.")
    s.status, s.confirmed_at = "CONFIRMED", datetime.now(timezone.utc)
    await ctx.session.flush()
    await ctx.session.refresh(s)
    return _out(ctx, s)


@router.post("/statements/{statement_id}/dispute", response_model=StatementOut, summary="Reseller: say the money did not arrive")
async def dispute(statement_id: UUID, body: Dispute, ctx: TenantContext = Depends(authorize("channel:manage"))):
    s = await _statement(ctx, statement_id, as_side="RESELLER")
    if s.status != "PAID":
        raise HTTPException(409, "You can only dispute a statement the owner marked as paid.")
    s.status, s.dispute_reason, s.disputed_at = "DISPUTED", body.reason.strip(), datetime.now(timezone.utc)
    await ctx.session.flush()
    await ctx.session.refresh(s)
    return _out(ctx, s)


@router.get("/summary", response_model=SummaryOut, summary="Totals: what I owe to resellers and what resellers owe me")
async def summary(ctx: TenantContext = Depends(authorize("channel:read"))):
    await _refresh(ctx)
    me, today = ctx.tenant.id, date.today()
    rows: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: {k: ZERO for k in ("upcoming", "unbilled", "to_pay", "awaiting_confirmation", "settled", "overdue")})

    for s in (await ctx.session.execute(select(ChannelSettlement))).scalars():
        r = rows[("OWNER" if s.supplier_tenant_id == me else "RESELLER", s.currency)]
        key = {"DUE": "to_pay", "DISPUTED": "to_pay", "PAID": "awaiting_confirmation", "CONFIRMED": "settled"}[s.status]
        r[key] += s.amount
        if st.overdue_days(s, today):
            r["overdue"] += s.amount
    unbilled = (await ctx.session.execute(select(ChannelLedger.supplier_tenant_id, ChannelLedger.currency, func.sum(ChannelLedger.amount))
                                          .outerjoin(ChannelSettlementItem, ChannelSettlementItem.ledger_id == ChannelLedger.id)
                                          .where(ChannelSettlementItem.ledger_id.is_(None)).group_by(ChannelLedger.supplier_tenant_id, ChannelLedger.currency))).all()
    for supplier, cur, total in unbilled:
        rows[("OWNER" if supplier == me else "RESELLER", cur)]["unbilled"] += total or ZERO

    live = (Booking.status == BookingStatus.CONFIRMED, Booking.check_out > today, Booking.channel_commission_amount > 0)
    for cur, total in (await ctx.session.execute(select(Booking.currency, func.sum(Booking.channel_commission_amount))
                                                 .where(Booking.channel_tenant_id.is_not(None), *live).group_by(Booking.currency))).all():
        rows[("OWNER", cur)]["upcoming"] += total or ZERO
    owners = {a.supplier_tenant_id for a in (await ctx.session.execute(select(ChannelAgreement).where(ChannelAgreement.reseller_tenant_id == me))).scalars()}
    for owner_id in owners:
        async with ch.owner_scope(owner_id, required=False) as oc:
            if oc is None:
                continue
            for cur, total in (await oc.session.execute(select(Booking.currency, func.sum(Booking.channel_commission_amount)).where(
                    Booking.tenant_id == owner_id, Booking.channel_tenant_id == me, *live).group_by(Booking.currency))).all():
                rows[("RESELLER", cur)]["upcoming"] += total or ZERO
    pick = lambda role: [MoneyRow(currency=cur, **v) for (r, cur), v in sorted(rows.items()) if r == role]
    return SummaryOut(as_owner=pick("OWNER"), as_reseller=pick("RESELLER"))
