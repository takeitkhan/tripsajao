"""Refund rules for bookings sold by a reseller. The owner's business-wide rules are kept in settings: "cancellation_policy"."""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import Tenant
from app.services.pricing import q

DEFAULT_RULES = [{"days_before": 7, "refund_percent": 100}, {"days_before": 3, "refund_percent": 50}, {"days_before": 0, "refund_percent": 0}]


def rules_of(tenant: Tenant) -> tuple[list[dict], bool]:
    raw = (tenant.settings_json or {}).get("cancellation_policy")
    if not raw:
        return [dict(r) for r in DEFAULT_RULES], True
    return sorted(({"days_before": int(r["days_before"]), "refund_percent": float(r["refund_percent"])} for r in raw), key=lambda r: -r["days_before"]), False


def today_for(tenant: Tenant) -> date:
    try:
        return datetime.now(ZoneInfo((tenant.settings_json or {}).get("timezone", "UTC"))).date()
    except Exception:  # noqa: BLE001
        return date.today()


def refund_for(tenant: Tenant, check_in: date, paid: Decimal) -> tuple[int, Decimal, Decimal]:
    """(days before check-in, percent, refund amount) for a cancellation made today."""
    days = (check_in - today_for(tenant)).days
    percent = Decimal(0)
    for r in rules_of(tenant)[0]:
        if days >= r["days_before"]:
            percent = Decimal(str(r["refund_percent"]))
            break
    return days, percent, q(paid * percent / 100)


def rule_text(percent: Decimal, days: int) -> str:
    p = f"{percent.normalize():f}"
    return (f"The guest gets {p}% of what they paid back, because check-in is in {days} day{'s' if days != 1 else ''}." if percent > 0
            else f"No refund, because check-in is in {days} day{'s' if days != 1 else ''}.")
