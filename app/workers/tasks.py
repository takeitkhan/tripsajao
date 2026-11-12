import asyncio
import logging
import smtplib
from decimal import Decimal
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import system_session
from app.core.redis import new_redis
from app.models import Booking, PartnerLedger, Tenant
from app.services.events import publish
from app.services.holds import hold_key, release_expired
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


async def _publish_released(released: list[tuple[UUID, UUID, UUID]]) -> None:
    redis = new_redis()
    try:
        for tenant_id, booking_id, unit_id in released:
            await redis.delete(hold_key(tenant_id, booking_id))
            await publish(tenant_id, "unit.released",
                          {"unit_id": unit_id, "booking_id": booking_id, "status": "AVAILABLE", "reason": "HOLD_EXPIRED"}, redis)
    finally:
        await redis.aclose()


@celery_app.task(name="app.workers.tasks.release_hold", bind=True, max_retries=5, acks_late=True)
def release_hold(self, tenant_id: str, booking_id: str) -> int:
    """Triggered by the Redis `expired` key event. Idempotent: no-op if already confirmed/cancelled/released."""
    async def run():
        async with system_session() as s:
            released = await release_expired(s, tenant_id=UUID(tenant_id), booking_id=UUID(booking_id))
        await _publish_released(released)
        return len(released)
    try:
        return asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.sweep_expired_holds")
def sweep_expired_holds() -> int:
    """Guarantee: releases every expired hold across all tenants, even if Redis events were missed."""
    async def run():
        async with system_session() as s:
            released = await release_expired(s)
        await _publish_released(released)
        return len(released)
    n = asyncio.run(run())
    if n:
        log.info("swept %s expired holds", n)
    return n


@celery_app.task(name="app.workers.tasks.reconcile_ledgers")
def reconcile_ledgers() -> list[str]:
    """Nightly aggregation: verifies each partner's last running balance == SUM(credit) - SUM(debit)."""
    async def run():
        problems: list[str] = []
        async with system_session() as s:
            sums = (await s.execute(select(PartnerLedger.partner_id, func.sum(PartnerLedger.credit - PartnerLedger.debit))
                                    .group_by(PartnerLedger.partner_id))).all()
            for partner_id, total in sums:
                last = (await s.execute(select(PartnerLedger.balance).where(PartnerLedger.partner_id == partner_id)
                                        .order_by(PartnerLedger.seq.desc()).limit(1))).scalar_one()
                if Decimal(last) != Decimal(total):
                    problems.append(f"partner {partner_id}: running {last} != sum {total}")
        return problems
    problems = asyncio.run(run())
    for p in problems:
        log.error("LEDGER DRIFT %s", p)
    return problems


@celery_app.task(name="app.workers.tasks.send_email", autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def send_email(to: str, subject: str, body: str, sender: str | None = None) -> None:
    import os
    host = os.getenv("SMTP_HOST")
    if not host:
        log.info("SMTP_HOST not set; email to %s skipped: %s", to, subject)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender or os.getenv("SMTP_FROM", "no-reply@example.com"), to, subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)


@celery_app.task(name="app.workers.tasks.send_booking_confirmation")
def send_booking_confirmation(tenant_id: str, booking_id: str) -> None:
    async def run():
        async with system_session() as s:
            b = (await s.execute(select(Booking).where(Booking.id == UUID(booking_id), Booking.tenant_id == UUID(tenant_id)))).scalar_one_or_none()
            t = (await s.execute(select(Tenant).where(Tenant.id == UUID(tenant_id)))).scalar_one_or_none()
            return (b, t)
    b, t = asyncio.run(run())
    if not b or not t:
        return
    email = (b.customer_info_json or {}).get("email")
    if email:
        send_email.delay(email, f"Booking {b.booking_ref} confirmed - {t.name}",
                         f"Hi {(b.customer_info_json or {}).get('name', '')},\n\nYour booking {b.booking_ref} "
                         f"({b.check_in} to {b.check_out}) is confirmed. Paid {b.paid_amount} of {b.total_amount} {b.currency}.\n")


@celery_app.task(name="app.workers.tasks.channel_statements")
def channel_statements() -> dict:
    """Daily: write commission for checked-out reseller bookings, reverse it for cancelled ones, and make due statements."""
    from app.services import settlement as st

    async def run():
        async with system_session() as s:
            a = await st.accrue(s)
            b = await st.settle(s)
        return {"ledger_rows": a, "statements": b}
    out = asyncio.run(run())
    if out["ledger_rows"] or out["statements"]:
        log.info("channel statements: %s", out)
    return out
