from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import LedgerType, PayoutRequest, PayoutStatus
from app.schemas.common import Page, Pagination
from app.schemas.partner import PayoutCreate, PayoutOut, PayoutReview
from app.services.ledger import add_entry, ledger_totals, reserved_for_payouts
from app.services.pricing import q

router = APIRouter(prefix="/payouts", tags=["payouts"])


@router.post("", response_model=PayoutOut, status_code=201, summary="Partner: request a payout")
async def request_payout(body: PayoutCreate, ctx: TenantContext = Depends(authorize("partner:self"))):
    pid = ctx.principal.partner_id
    min_payout = Decimal(str(ctx.tenant.settings_json.get("min_payout", 1000)))
    if body.amount < min_payout:
        raise HTTPException(422, f"Minimum payout is {min_payout}")
    # serialise concurrent requests from the same partner
    await add_lock(ctx, pid)
    _, _, balance = await ledger_totals(ctx.session, pid)
    available = q(balance - await reserved_for_payouts(ctx.session, pid))
    if body.amount > available:
        raise HTTPException(422, f"Amount exceeds available balance ({available})")
    req = PayoutRequest(tenant_id=ctx.tenant.id, partner_id=pid, amount=body.amount,
                        payout_details_json=body.payout_details.model_dump(mode="json"))
    return await persist(ctx.session, req)


async def add_lock(ctx: TenantContext, partner_id: UUID) -> None:
    from app.models import Partner
    await ctx.session.execute(select(Partner.id).where(Partner.id == partner_id).with_for_update())


@router.get("", response_model=Page[PayoutOut], summary="List payout requests (admin: all, partner: own)")
async def list_payouts(status_: PayoutStatus | None = Query(None, alias="status"), pg: Pagination = Depends(),
                       ctx: TenantContext = Depends(authorize("payouts:read", "partner:self"))):
    stmt = select(PayoutRequest).where(PayoutRequest.tenant_id == ctx.tenant.id).order_by(PayoutRequest.created_at.desc())
    if ctx.principal.kind == "partner":
        stmt = stmt.where(PayoutRequest.partner_id == ctx.principal.partner_id)
    if status_:
        stmt = stmt.where(PayoutRequest.status == status_)
    return await paginate(ctx.session, stmt, pg)


async def _pending_review(ctx: TenantContext, payout_id: UUID, allowed: PayoutStatus) -> PayoutRequest:
    p = (await ctx.session.execute(select(PayoutRequest).where(
        PayoutRequest.id == payout_id, PayoutRequest.tenant_id == ctx.tenant.id).with_for_update())).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Payout not found")
    if p.status != allowed:
        raise HTTPException(409, f"Payout is {p.status.value}; expected {allowed.value}")
    return p


@router.post("/{payout_id}/approve", response_model=PayoutOut, summary="Admin: approve (funds stay reserved)")
async def approve(payout_id: UUID, body: PayoutReview, ctx: TenantContext = Depends(authorize("payouts:approve"))):
    p = await _pending_review(ctx, payout_id, PayoutStatus.PENDING)
    _, _, balance = await ledger_totals(ctx.session, p.partner_id)
    if p.amount > q(balance - await reserved_for_payouts(ctx.session, p.partner_id, exclude=p.id)):
        raise HTTPException(409, "Partner balance no longer covers this payout (e.g. after a cancellation)")
    p.status, p.reviewed_by, p.review_note = PayoutStatus.APPROVED, ctx.principal.user_id, body.note
    return await persist(ctx.session, p)


@router.post("/{payout_id}/reject", response_model=PayoutOut, summary="Admin: reject a pending payout")
async def reject(payout_id: UUID, body: PayoutReview, ctx: TenantContext = Depends(authorize("payouts:approve"))):
    p = await _pending_review(ctx, payout_id, PayoutStatus.PENDING)
    p.status, p.reviewed_by, p.review_note = PayoutStatus.REJECTED, ctx.principal.user_id, body.note
    return await persist(ctx.session, p)


@router.post("/{payout_id}/mark-paid", response_model=PayoutOut, summary="Admin: record settlement -> debits the ledger")
async def mark_paid(payout_id: UUID, body: PayoutReview, ctx: TenantContext = Depends(authorize("payouts:approve"))):
    p = await _pending_review(ctx, payout_id, PayoutStatus.APPROVED)
    await add_entry(ctx.session, tenant_id=ctx.tenant.id, partner_id=p.partner_id, payout_id=p.id,
                    transaction_type=LedgerType.PAYOUT, debit=p.amount, note=body.note or "Payout settled")
    p.status, p.paid_at = PayoutStatus.PAID, datetime.now(timezone.utc)
    return await persist(ctx.session, p)
