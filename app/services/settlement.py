"""Commission book and statements between an owner and a reseller.

  1. ACCRUAL: once a reseller's confirmed booking has been checked out, its commission is written to the ledger.
  2. REVERSAL: if such a booking is cancelled later, a negative row is added (rows are never edited or deleted).
  3. STATEMENT: unbilled ledger rows are gathered into a statement with a due date, MONTHLY (all finished months, due on the agreed
     day of this month) or PER_BOOKING (one statement per booking, due the agreed number of days after check-out).
  4. The owner marks a statement paid; the reseller confirms receipt (or disputes it); the owner can pay again after a dispute.

Everything here takes a session that is either bound to the owner's business (so row level security applies) or the cross-business
system session used by the daily sweep. `today` can be passed in for tests."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (Booking, BookingStatus, ChannelAgreement, ChannelLedger, ChannelSettlement, ChannelSettlementItem, Property)

OVERDUE_STATUSES = ("DUE",)
TWO = Decimal("0.01")


def _today() -> date:
    return date.today()


async def accrue(session: AsyncSession, *, supplier_id: UUID | None = None, today: date | None = None) -> int:
    """Write ACCRUAL rows for checked-out reseller bookings and REVERSAL rows for cancelled ones. Safe to repeat."""
    today = today or _today()
    made = 0
    q = (select(Booking, Property.name).join(Property, (Property.tenant_id == Booking.tenant_id) & (Property.id == Booking.property_id))
         .where(Booking.channel_tenant_id.is_not(None), Booking.channel_agreement_id.is_not(None), Booking.status == BookingStatus.CONFIRMED,
                Booking.check_out <= today, Booking.channel_commission_amount > 0,
                ~exists(select(ChannelLedger.id).where(ChannelLedger.booking_id == Booking.id, ChannelLedger.entry_type == "ACCRUAL").correlate(Booking))))
    if supplier_id:
        q = q.where(Booking.tenant_id == supplier_id)
    for b, prop_name in (await session.execute(q.limit(2000))).all():
        res = await session.execute(pg_insert(ChannelLedger).values(
            agreement_id=b.channel_agreement_id, supplier_tenant_id=b.tenant_id, reseller_tenant_id=b.channel_tenant_id, booking_id=b.id,
            entry_type="ACCRUAL", amount=b.channel_commission_amount, currency=b.currency, event_date=b.check_out, booking_ref=b.booking_ref,
            property_name=prop_name, guest_name=str((b.customer_info_json or {}).get("name", ""))[:200], check_in=b.check_in, check_out=b.check_out,
        ).on_conflict_do_nothing(constraint="uq_channel_ledger_booking_type"))
        made += res.rowcount or 0

    acc = ChannelLedger
    q = (select(Booking, acc).join(acc, (acc.booking_id == Booking.id) & (acc.entry_type == "ACCRUAL"))
         .where(Booking.status == BookingStatus.CANCELLED,
                ~exists(select(ChannelLedger.id).where(ChannelLedger.booking_id == Booking.id, ChannelLedger.entry_type == "REVERSAL").correlate(Booking))))
    if supplier_id:
        q = q.where(Booking.tenant_id == supplier_id)
    for b, a in (await session.execute(q.limit(2000))).all():
        res = await session.execute(pg_insert(ChannelLedger).values(
            agreement_id=a.agreement_id, supplier_tenant_id=a.supplier_tenant_id, reseller_tenant_id=a.reseller_tenant_id, booking_id=b.id,
            entry_type="REVERSAL", amount=-a.amount, currency=a.currency, event_date=today, booking_ref=a.booking_ref, property_name=a.property_name,
            guest_name=a.guest_name, check_in=a.check_in, check_out=a.check_out,
        ).on_conflict_do_nothing(constraint="uq_channel_ledger_booking_type"))
        made += res.rowcount or 0
    await session.flush()
    return made


def _due_in_month(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(day, 1), monthrange(year, month)[1]))


async def settle(session: AsyncSession, *, supplier_id: UUID | None = None, today: date | None = None) -> int:
    """Gather unbilled ledger rows into statements, as each agreement says. Safe to repeat."""
    today = today or _today()
    month_start = today.replace(day=1)
    rows = (await session.execute(
        select(ChannelLedger).outerjoin(ChannelSettlementItem, ChannelSettlementItem.ledger_id == ChannelLedger.id)
        .where(ChannelSettlementItem.ledger_id.is_(None), *( [ChannelLedger.supplier_tenant_id == supplier_id] if supplier_id else [] ))
        .order_by(ChannelLedger.event_date, ChannelLedger.created_at))).scalars().all()
    by_ag: dict[UUID, list[ChannelLedger]] = defaultdict(list)
    for r in rows:
        by_ag[r.agreement_id].append(r)
    made = 0
    for ag_id, entries in by_ag.items():
        ag = await session.get(ChannelAgreement, ag_id)
        if ag is None:
            continue
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"settle:{ag_id}"})
        for currency in sorted({e.currency for e in entries}):
            part = [e for e in entries if e.currency == currency]
            if ag.settlement_mode == "PER_BOOKING":
                made += await _per_booking(session, ag, part, currency)
            else:
                part = [e for e in part if e.event_date < month_start]
                net = sum((e.amount for e in part), Decimal(0))
                if part and net > 0:
                    made += await _make(session, ag, part, net, currency, "MONTHLY", part[0].event_date, month_start - timedelta(days=1),
                                        _due_in_month(month_start.year, month_start.month, ag.settlement_day))
    return made


async def _per_booking(session, ag, part, currency) -> int:
    groups: dict[UUID, list[ChannelLedger]] = defaultdict(list)
    for e in part:
        groups[e.booking_id].append(e)
    credits = [g for g in groups.values() if sum((e.amount for e in g), Decimal(0)) < 0]
    made = 0
    for g in groups.values():
        net = sum((e.amount for e in g), Decimal(0))
        if net <= 0:
            continue
        use = list(g)
        if credits:                                    # an earlier refund of commission is taken off the next statement
            extra = [e for c in credits for e in c]
            if net + sum((e.amount for e in extra), Decimal(0)) > 0:
                use += extra
                net += sum((e.amount for e in extra), Decimal(0))
                credits = []
        acc = next((e for e in g if e.entry_type == "ACCRUAL"), g[0])
        made += await _make(session, ag, use, net, currency, "PER_BOOKING", min(e.event_date for e in use), acc.check_out,
                            acc.check_out + timedelta(days=ag.settlement_day))
    return made


async def _make(session, ag, entries, amount, currency, mode, start, end, due) -> int:
    try:
        async with session.begin_nested():
            s = ChannelSettlement(agreement_id=ag.id, supplier_tenant_id=ag.supplier_tenant_id, reseller_tenant_id=ag.reseller_tenant_id,
                                  supplier_name=ag.supplier_name, reseller_name=ag.reseller_name, mode=mode, period_start=start, period_end=end,
                                  amount=amount.quantize(TWO), currency=currency, due_date=due, status="DUE")
            session.add(s)
            await session.flush()
            session.add_all([ChannelSettlementItem(ledger_id=e.id, settlement_id=s.id, supplier_tenant_id=ag.supplier_tenant_id,
                                                   reseller_tenant_id=ag.reseller_tenant_id) for e in entries])
            await session.flush()
        return 1
    except IntegrityError:                              # another request billed these rows a moment ago
        return 0


async def refresh_owner(session: AsyncSession, supplier_id: UUID, today: date | None = None) -> None:
    await accrue(session, supplier_id=supplier_id, today=today)
    await settle(session, supplier_id=supplier_id, today=today)


def overdue_days(s: ChannelSettlement, today: date | None = None) -> int:
    today = today or _today()
    return (today - s.due_date).days if s.status in OVERDUE_STATUSES and s.due_date < today else 0
