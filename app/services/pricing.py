"""Dynamic pricing engine (pure functions + a small DB loader).

Per-night algorithm
  1. base = weekend_price if night's weekday in cfg.weekend_days else weekday_price
  2. rules matching (date in [start,end] and applies_to in {ALL, day type}) are collected
  3. if any OVERRIDE rules match, the highest `priority` one replaces the base
  4. all matching SURCHARGE_PERCENT rules are summed and applied to the base; SURCHARGE_FLAT are added
  Night price = round_half_up(base * (1 + pct/100) + flat, 2).   A stay prices nights [check_in, check_out).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PricingRule
from app.schemas.inventory import SeasonalConfig

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_NIGHTS = 60


def q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class NightPrice:
    night: date
    day_type: str
    base_price: Decimal
    applied_rules: list[str]
    price: Decimal


@dataclass(frozen=True)
class StayQuote:
    currency: str
    nights: list[NightPrice]
    total: Decimal


def price_for_night(weekday_price: Decimal, weekend_price: Decimal, cfg: SeasonalConfig, night: date) -> NightPrice:
    is_weekend = night.weekday() in cfg.weekend_days
    day_type = "WEEKEND" if is_weekend else "WEEKDAY"
    base = Decimal(weekend_price if is_weekend else weekday_price)
    applied: list[str] = []

    matching = [r for r in cfg.rules
                if r.start_date <= night <= r.end_date and r.applies_to in ("ALL", day_type)]
    overrides = sorted((r for r in matching if r.kind == "OVERRIDE"), key=lambda r: r.priority, reverse=True)
    base_after_override = base
    if overrides:
        base_after_override = overrides[0].value
        applied.append(overrides[0].name)

    pct = sum((r.value for r in matching if r.kind == "SURCHARGE_PERCENT"), Decimal(0))
    flat = sum((r.value for r in matching if r.kind == "SURCHARGE_FLAT"), Decimal(0))
    applied += [r.name for r in matching if r.kind != "OVERRIDE"]

    price = q(base_after_override * (Decimal(1) + pct / Decimal(100)) + flat)
    return NightPrice(night, day_type, q(base), applied, price)


def quote_stay(rule: PricingRule | None, check_in: date, check_out: date) -> StayQuote:
    if rule is None:
        raise HTTPException(422, "Pricing is not configured for this unit")
    nights_count = (check_out - check_in).days
    if nights_count < 1:
        raise HTTPException(422, "check_out must be after check_in")
    if nights_count > MAX_NIGHTS:
        raise HTTPException(422, f"Maximum stay is {MAX_NIGHTS} nights")
    cfg = SeasonalConfig.model_validate(rule.seasonal_price_json or {})
    nights = [price_for_night(rule.weekday_price, rule.weekend_price, cfg, check_in + timedelta(days=i))
              for i in range(nights_count)]
    return StayQuote(rule.currency, nights, q(sum((n.price for n in nights), Decimal(0))))


async def quote_for_unit(session: AsyncSession, tenant_id: UUID, unit_id: UUID, check_in: date, check_out: date) -> StayQuote:
    rule = (await session.execute(
        select(PricingRule).where(PricingRule.tenant_id == tenant_id, PricingRule.unit_id == unit_id)
    )).scalar_one_or_none()
    return quote_stay(rule, check_in, check_out)
