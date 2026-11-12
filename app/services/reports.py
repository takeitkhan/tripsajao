"""Numbers for the business owner's Overview page."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text


def _tz(tenant) -> tuple[str, date]:
    name = (tenant.settings_json or {}).get("timezone") or "UTC"
    try:
        today = datetime.now(ZoneInfo(name)).date()
    except Exception:
        name, today = "UTC", datetime.now(ZoneInfo("UTC")).date()
    return name, today


async def overview(session, tenant, days: int) -> dict:
    tz, today = _tz(tenant)
    since = today - timedelta(days=days - 1)
    A = {"t": tenant.id, "tz": tz, "today": today, "since": since}
    q = lambda sql, **p: session.execute(text(sql), {**A, **p})  # noqa: E731

    cur = (await q("SELECT currency FROM bookings WHERE tenant_id = :t GROUP BY currency ORDER BY count(*) DESC LIMIT 1")).scalar_one_or_none() \
        or (tenant.settings_json.get("company", {}) or {}).get("currency") or "USD"
    B = {"cur": cur}
    created = "(b.created_at AT TIME ZONE :tz)::date"

    k = (await q(f"""SELECT count(*) FILTER (WHERE status = 'CONFIRMED' AND {created.replace('b.', '')} >= :since),
                            coalesce(sum(total_amount) FILTER (WHERE status = 'CONFIRMED' AND {created.replace('b.', '')} >= :since), 0),
                            coalesce(sum(paid_amount) FILTER (WHERE status = 'CONFIRMED' AND {created.replace('b.', '')} >= :since), 0),
                            coalesce(sum(total_amount - paid_amount) FILTER (WHERE status = 'CONFIRMED' AND check_out >= :today), 0),
                            count(*) FILTER (WHERE status = 'CANCELLED' AND {created.replace('b.', '')} >= :since),
                            count(*) FILTER (WHERE status = 'HOLD' AND hold_expires_at > now()),
                            count(*) FILTER (WHERE status = 'CONFIRMED' AND check_in BETWEEN :today AND :today + 6),
                            coalesce(avg(check_out - check_in) FILTER (WHERE status = 'CONFIRMED' AND {created.replace('b.', '')} >= :since), 0)
                     FROM bookings WHERE tenant_id = :t AND currency = :cur""", **B)).one()
    total_units = (await q("SELECT count(*) FROM units WHERE tenant_id = :t AND is_active AND type <> 'WHOLE_BOAT'")).scalar_one()
    busy_now = (await q("""SELECT count(DISTINCT unit_id) FROM bookings WHERE tenant_id = :t AND (status = 'CONFIRMED' OR (status = 'HOLD' AND hold_expires_at > now()))
                           AND check_in <= :today AND check_out > :today""")).scalar_one()
    occ = [{"day": str(d), "booked": n} for d, n in (await q("""SELECT g::date, count(DISTINCT b.unit_id) FROM generate_series(CAST(:today AS date), CAST(:today AS date) + 13, interval '1 day') g
            LEFT JOIN bookings b ON b.tenant_id = :t AND (b.status = 'CONFIRMED' OR (b.status = 'HOLD' AND b.hold_expires_at > now()))
                 AND b.check_in <= g::date AND b.check_out > g::date GROUP BY g ORDER BY g""")).all()]
    daily = [{"day": str(d), "bookings": n, "value": str(v)} for d, n, v in (await q(f"""
            SELECT g::date, count(b.id), coalesce(sum(b.total_amount), 0)
            FROM generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') g
            LEFT JOIN bookings b ON b.tenant_id = :t AND b.status <> 'CANCELLED' AND b.currency = :cur AND {created} = g::date
            GROUP BY g ORDER BY g""", **B)).all()]
    by_prop = [{"name": n, "bookings": c, "value": str(v)} for n, c, v in (await q(f"""
            SELECT p.name, count(b.id), coalesce(sum(b.total_amount), 0) FROM bookings b JOIN properties p ON p.id = b.property_id
            WHERE b.tenant_id = :t AND b.status = 'CONFIRMED' AND b.currency = :cur AND {created} >= :since GROUP BY p.name ORDER BY 2 DESC, 3 DESC LIMIT 6""", **B)).all()]
    status_counts = dict((await q(f"""SELECT CASE WHEN b.status = 'HOLD' THEN 'On hold' WHEN b.status = 'CONFIRMED' THEN 'Confirmed' ELSE 'Cancelled' END, count(*)
            FROM bookings b WHERE b.tenant_id = :t AND b.currency = :cur AND {created} >= :since AND (b.status <> 'HOLD' OR b.hold_expires_at > now()) GROUP BY 1""", **B)).all())
    src = (await q(f"""SELECT count(*) FILTER (WHERE b.partner_id IS NULL), coalesce(sum(b.total_amount) FILTER (WHERE b.partner_id IS NULL), 0),
                              count(*) FILTER (WHERE b.partner_id IS NOT NULL), coalesce(sum(b.total_amount) FILTER (WHERE b.partner_id IS NOT NULL), 0)
            FROM bookings b WHERE b.tenant_id = :t AND b.status = 'CONFIRMED' AND b.currency = :cur AND {created} >= :since""", **B)).one()
    partners = [{"name": n, "bookings": c, "sales": str(s), "commission": str(cm)} for n, c, s, cm in (await q(f"""
            SELECT pa.name, count(b.id), coalesce(sum(b.total_amount), 0), coalesce(sum(b.commission_amount), 0) FROM bookings b JOIN partners pa ON pa.id = b.partner_id
            WHERE b.tenant_id = :t AND b.status = 'CONFIRMED' AND b.currency = :cur AND {created} >= :since GROUP BY pa.name ORDER BY 3 DESC LIMIT 5""", **B)).all()]
    arrivals = [{"booking_ref": r[0], "guest": r[1], "unit": r[2], "property": r[3], "check_in": str(r[4]), "nights": r[5], "balance": str(r[6])} for r in (await q("""
            SELECT b.booking_ref, b.customer_info_json->>'name', u.unit_name, p.name, b.check_in, b.check_out - b.check_in, b.total_amount - b.paid_amount
            FROM bookings b JOIN units u ON u.id = b.unit_id JOIN properties p ON p.id = b.property_id
            WHERE b.tenant_id = :t AND b.status = 'CONFIRMED' AND b.check_in BETWEEN :today AND :today + 6 ORDER BY b.check_in, p.name, u.unit_name LIMIT 10""")).all()]
    return {
        "currency": cur, "days": days, "since": str(since), "today": str(today),
        "kpis": {"bookings": k[0], "booked_value": str(k[1]), "collected": str(k[2]), "outstanding": str(k[3]), "cancelled": k[4], "active_holds": k[5],
                 "arrivals_7d": k[6], "avg_stay_nights": round(float(k[7]), 1), "total_units": total_units, "occupied_now": busy_now,
                 "occupancy_now_percent": round(100 * busy_now / total_units) if total_units else 0},
        "occupancy_next_14_days": [{**o, "total": total_units, "percent": round(100 * o["booked"] / total_units) if total_units else 0} for o in occ],
        "daily": daily, "by_property": by_prop, "by_status": status_counts,
        "by_source": {"direct": {"bookings": src[0], "value": str(src[1])}, "partners": {"bookings": src[2], "value": str(src[3])}},
        "top_partners": partners, "arrivals": arrivals,
    }
