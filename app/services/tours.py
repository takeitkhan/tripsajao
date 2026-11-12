"""Event budget arithmetic and small helpers for packages, events, vendors and budgets."""
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:120] or "untitled"


def last_day(start: date, days: int) -> date:
    return start + timedelta(days=max(days, 1) - 1)


def compute(lines: list[dict], people: int, margin_percent: Decimal) -> dict:
    """Every line = quantity x price (x people when 'per person'). Selling price = cost plus the margin on top of cost.
    Money is rounded per line first, so what is printed always adds up to the total."""
    out, cost = [], Decimal(0)
    for ln in lines:
        mult = Decimal(people) if ln.get("per_person") else Decimal(1)
        total = money(Decimal(str(ln["qty"])) * Decimal(str(ln["unit_price"])) * mult)
        cost += total
        out.append({**ln, "line_total": total})
    cost = money(cost)
    margin = money(cost * Decimal(margin_percent) / 100)
    sell = cost + margin
    p = Decimal(max(people, 1))
    return {"lines": out, "cost_total": cost, "margin_amount": margin, "sell_total": sell,
            "cost_per_person": money(cost / p), "sell_per_person": money(sell / p)}
