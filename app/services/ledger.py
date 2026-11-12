"""Partner ledger: append-only double-entry-style statement with running balance.

Commission accrues PROPORTIONALLY to money actually received, so deposits/partial payments are handled
correctly and rounding never drifts (we always compute the cumulative target and post only the delta).
Cancellations post a reversal. Payouts post a debit when marked PAID.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, CommissionType, LedgerType, Partner, PartnerLedger, PayoutRequest, PayoutStatus
from app.services.pricing import ZERO, q


def commission_for(partner: Partner, total: Decimal) -> Decimal:
    """Commission on the full booking value (snapshotted onto the booking at hold time)."""
    if partner.commission_type == CommissionType.PERCENT:
        return q(total * partner.commission_value / Decimal(100))
    return q(min(partner.commission_value, total))       # FLAT per booking, never more than the booking


async def add_entry(session: AsyncSession, *, tenant_id: UUID, partner_id: UUID, transaction_type: LedgerType,
                    credit: Decimal = ZERO, debit: Decimal = ZERO, booking_id: UUID | None = None,
                    payout_id: UUID | None = None, note: str | None = None,
                    event_booking_id: UUID | None = None) -> PartnerLedger:
    # Row lock serialises concurrent postings for one partner so running balances stay consistent.
    await session.execute(select(Partner.id).where(Partner.id == partner_id, Partner.tenant_id == tenant_id).with_for_update())
    last = (await session.execute(
        select(PartnerLedger.balance).where(PartnerLedger.partner_id == partner_id)
        .order_by(PartnerLedger.seq.desc()).limit(1))).scalar_one_or_none() or ZERO
    entry = PartnerLedger(tenant_id=tenant_id, partner_id=partner_id, booking_id=booking_id, payout_id=payout_id, event_booking_id=event_booking_id,
                          credit=q(credit), debit=q(debit), balance=q(last + credit - debit),
                          transaction_type=transaction_type, note=note)
    session.add(entry)
    await session.flush()
    return entry


async def sync_booking_commission(session: AsyncSession, booking: Booking, *, cancelled: bool = False) -> None:
    """Bring the ledger in line with what the booking has earned so far."""
    if booking.partner_id is None or booking.commission_amount <= 0:
        return
    if cancelled or booking.total_amount <= 0:
        target = ZERO
    else:
        ratio = min(booking.paid_amount / booking.total_amount, Decimal(1))
        target = q(booking.commission_amount * ratio)
    credited = (await session.execute(
        select(func.coalesce(func.sum(PartnerLedger.credit - PartnerLedger.debit), 0))
        .where(PartnerLedger.booking_id == booking.id,
               PartnerLedger.transaction_type.in_([LedgerType.COMMISSION, LedgerType.COMMISSION_REVERSAL])))).scalar_one()
    delta = q(target - Decimal(credited))
    if delta > 0:
        await add_entry(session, tenant_id=booking.tenant_id, partner_id=booking.partner_id, booking_id=booking.id,
                        transaction_type=LedgerType.COMMISSION, credit=delta,
                        note=f"Commission on {booking.booking_ref}")
    elif delta < 0:
        await add_entry(session, tenant_id=booking.tenant_id, partner_id=booking.partner_id, booking_id=booking.id,
                        transaction_type=LedgerType.COMMISSION_REVERSAL, debit=-delta,
                        note=f"Reversal on {booking.booking_ref}")


async def ledger_totals(session: AsyncSession, partner_id: UUID) -> tuple[Decimal, Decimal, Decimal]:
    credit, debit = (await session.execute(
        select(func.coalesce(func.sum(PartnerLedger.credit), 0), func.coalesce(func.sum(PartnerLedger.debit), 0))
        .where(PartnerLedger.partner_id == partner_id))).one()
    return q(Decimal(credit)), q(Decimal(debit)), q(Decimal(credit) - Decimal(debit))


async def reserved_for_payouts(session: AsyncSession, partner_id: UUID, exclude: UUID | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(PayoutRequest.amount), 0)).where(
        PayoutRequest.partner_id == partner_id,
        PayoutRequest.status.in_([PayoutStatus.PENDING, PayoutStatus.APPROVED]))
    if exclude:
        stmt = stmt.where(PayoutRequest.id != exclude)
    return q(Decimal((await session.execute(stmt)).scalar_one()))
