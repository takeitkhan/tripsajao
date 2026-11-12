"""Customers: one list of everyone a business has dealt with, with booking figures counted from the bookings."""
import csv
import io
import re
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from app.schemas.crm import CustomerFilters
from app.services.reports import _tz

STATS = """
 SELECT lower(b.customer_info_json->>'email') AS em,
        count(*) FILTER (WHERE b.status = 'CONFIRMED') AS stays,
        count(*) FILTER (WHERE b.status = 'CANCELLED') AS cancelled,
        coalesce(sum(b.total_amount) FILTER (WHERE b.status = 'CONFIRMED' AND b.currency = :cur), 0) AS spent,
        max(b.check_out) FILTER (WHERE b.status = 'CONFIRMED') AS last_stay,
        min(b.check_in) FILTER (WHERE b.status = 'CONFIRMED' AND b.check_in >= :today) AS next_stay,
        max(b.created_at) AS last_booked
 FROM bookings b WHERE b.tenant_id = :t AND b.customer_info_json->>'email' IS NOT NULL GROUP BY 1"""

SORTS = {"recent": "s.last_booked DESC NULLS LAST, c.created_at DESC", "spent": "coalesce(s.spent, 0) DESC, c.name",
         "stays": "coalesce(s.stays, 0) DESC, c.name", "name": "lower(c.name), c.email"}


async def sync_from_bookings(session, tenant_id: UUID) -> None:
    """Every guest who booked becomes a customer (once, by e-mail). Existing customers are left as they are."""
    await session.execute(text("""
        INSERT INTO customers (id, tenant_id, email, name, phone, source, created_at, updated_at)
        SELECT gen_random_uuid(), :t, g.em, g.name, g.phone, 'BOOKING', g.created_at, now() FROM (
          SELECT DISTINCT ON (lower(b.customer_info_json->>'email'))
                 lower(trim(b.customer_info_json->>'email')) AS em, left(coalesce(nullif(trim(b.customer_info_json->>'name'), ''), 'Guest'), 200) AS name,
                 left(nullif(trim(b.customer_info_json->>'phone'), ''), 40) AS phone, b.created_at
          FROM bookings b WHERE b.tenant_id = :t AND nullif(trim(b.customer_info_json->>'email'), '') IS NOT NULL
          ORDER BY lower(b.customer_info_json->>'email'), b.created_at DESC) g
        ON CONFLICT (tenant_id, email) DO NOTHING"""), {"t": tenant_id})


async def currency_of(session, tenant) -> str:
    cur = (await session.execute(text("SELECT currency FROM bookings WHERE tenant_id = :t GROUP BY currency ORDER BY count(*) DESC LIMIT 1"),
                                 {"t": tenant.id})).scalar_one_or_none()
    return cur or ((tenant.settings_json or {}).get("company", {}) or {}).get("currency") or "USD"


def _where(f: CustomerFilters, params: dict) -> str:
    w = ["c.tenant_id = :t"]
    if f.q:
        like = "%" + re.sub(r"([\\%_])", r"\\\1", f.q.strip().lower()) + "%"
        params["like"] = like
        w.append("(lower(c.name) LIKE :like OR c.email LIKE :like OR coalesce(c.phone, '') LIKE :like)")
    if f.tag:
        params["tag"] = " ".join(f.tag.split()).lower()
        w.append("jsonb_exists(c.tags, :tag)")
    if f.source:
        params["source"] = f.source
        w.append("c.source = :source")
    if f.min_stays is not None:
        params["min_stays"] = f.min_stays
        w.append("coalesce(s.stays, 0) >= :min_stays")
    if f.max_stays is not None:
        params["max_stays"] = f.max_stays
        w.append("coalesce(s.stays, 0) <= :max_stays")
    if f.inactive_days:
        params["cutoff"] = params["today"] - timedelta(days=f.inactive_days)
        w.append("s.last_stay IS NOT NULL AND s.last_stay < :cutoff AND s.next_stay IS NULL")
    return " AND ".join(w)


SELECT = f"""
 SELECT c.id, c.name, c.email, c.phone, c.tags, c.notes, c.source, c.created_at,
        coalesce(s.stays, 0) AS stays, coalesce(s.cancelled, 0) AS cancelled, coalesce(s.spent, 0) AS spent,
        s.last_stay, s.next_stay, s.last_booked
 FROM customers c LEFT JOIN ({STATS}) s ON s.em = c.email"""


def _row(r, cur: str) -> dict:
    return {"id": r.id, "name": r.name, "email": r.email, "phone": r.phone, "tags": list(r.tags or []), "notes": r.notes, "source": r.source,
            "stays": r.stays, "cancelled": r.cancelled, "total_spent": Decimal(r.spent), "currency": cur, "last_stay": r.last_stay,
            "next_stay": r.next_stay, "last_booked_at": r.last_booked, "created_at": r.created_at}


async def _params(session, tenant) -> dict:
    return {"t": tenant.id, "today": _tz(tenant)[1], "cur": await currency_of(session, tenant)}


async def list_customers(session, tenant, f: CustomerFilters, limit: int, offset: int) -> tuple[list[dict], int]:
    await sync_from_bookings(session, tenant.id)
    p = await _params(session, tenant)
    w = _where(f, p)
    total = (await session.execute(text(f"SELECT count(*) FROM ({SELECT} WHERE {w}) x"), p)).scalar_one()
    rows = (await session.execute(text(f"{SELECT} WHERE {w} ORDER BY {SORTS[f.sort]} LIMIT :lim OFFSET :off"), {**p, "lim": limit, "off": offset})).all()
    return [_row(r, p["cur"]) for r in rows], total


async def get_customer(session, tenant, customer_id: UUID) -> dict | None:
    await sync_from_bookings(session, tenant.id)
    p = await _params(session, tenant)
    r = (await session.execute(text(f"{SELECT} WHERE c.tenant_id = :t AND c.id = :cid"), {**p, "cid": customer_id})).first()
    if r is None:
        return None
    out = _row(r, p["cur"])
    rows = (await session.execute(text("""
        SELECT b.id, b.booking_ref, p.name AS property, u.unit_name, b.check_in, b.check_out, b.status, b.total_amount, b.paid_amount, b.currency
        FROM bookings b JOIN units u ON u.id = b.unit_id JOIN properties p ON p.id = b.property_id
        WHERE b.tenant_id = :t AND lower(b.customer_info_json->>'email') = :em ORDER BY b.check_in DESC LIMIT 200"""), {"t": tenant.id, "em": r.email})).all()
    out["bookings"] = [{"id": x.id, "booking_ref": x.booking_ref, "property": x.property, "unit": x.unit_name, "check_in": x.check_in, "check_out": x.check_out,
                        "status": x.status if isinstance(x.status, str) else x.status.value, "total_amount": x.total_amount, "paid_amount": x.paid_amount,
                        "currency": x.currency} for x in rows]
    return out


async def matching_ids(session, tenant, f: CustomerFilters, cap: int = 5000) -> list[UUID]:
    await sync_from_bookings(session, tenant.id)
    p = await _params(session, tenant)
    w = _where(f, p)
    rows = (await session.execute(text(f"SELECT c.id FROM customers c LEFT JOIN ({STATS}) s ON s.em = c.email WHERE {w} LIMIT :cap"), {**p, "cap": cap})).all()
    return [r.id for r in rows]


_FORMULA = re.compile(r"^[=\-@\t\r]")
_PHONE = re.compile(r"^\+[\d\s\-]+$")


def _safe(v) -> str:
    """Stop spreadsheet programs from running a cell that starts like a formula (a guest could type one as their name)."""
    s = "" if v is None else str(v)
    if _FORMULA.match(s) or (s.startswith("+") and not _PHONE.match(s)):
        return "'" + s
    return s


async def export_csv(session, tenant, f: CustomerFilters) -> str:
    await sync_from_bookings(session, tenant.id)
    p = await _params(session, tenant)
    w = _where(f, p)
    rows = (await session.execute(text(f"{SELECT} WHERE {w} ORDER BY {SORTS[f.sort]} LIMIT 50000"), p)).all()
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["Name", "Email", "Phone", "Tags", "Source", "Confirmed stays", "Cancelled", f"Total spent ({p['cur']})", "Last stay", "Next stay", "Notes", "Added"])
    for r in rows:
        wr.writerow([_safe(r.name), _safe(r.email), _safe(r.phone), _safe(", ".join(r.tags or [])), r.source, r.stays, r.cancelled, f"{Decimal(r.spent):.2f}",
                     r.last_stay or "", r.next_stay or "", _safe(r.notes), r.created_at.date().isoformat()])
    return "﻿" + buf.getvalue()          # the mark lets Excel read Bengali correctly
