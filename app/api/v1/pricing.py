from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import TenantContext, authorize, get_or_404, persist
from app.models import PricingRule, Unit
from app.schemas.inventory import NightPriceOut, PricingRuleIn, PricingRuleOut, QuoteOut, QuoteRequest
from app.services.pricing import quote_for_unit

router = APIRouter(prefix="/pricing", tags=["pricing"])


async def _rule(ctx: TenantContext, unit_id: UUID) -> PricingRule | None:
    return (await ctx.session.execute(select(PricingRule).where(
        PricingRule.tenant_id == ctx.tenant.id, PricingRule.unit_id == unit_id))).scalar_one_or_none()


@router.get("/units/{unit_id}", response_model=PricingRuleOut, summary="Get pricing rule of a unit")
async def get_pricing(unit_id: UUID, ctx: TenantContext = Depends(authorize("pricing:read"))):
    await get_or_404(ctx, Unit, unit_id, "Unit")
    rule = await _rule(ctx, unit_id)
    if rule is None:
        from fastapi import HTTPException
        raise HTTPException(404, "No pricing configured")
    return rule


@router.put("/units/{unit_id}", response_model=PricingRuleOut, summary="Create/replace weekday, weekend & seasonal pricing")
async def put_pricing(unit_id: UUID, body: PricingRuleIn, ctx: TenantContext = Depends(authorize("pricing:write"))):
    await get_or_404(ctx, Unit, unit_id, "Unit")
    rule = await _rule(ctx, unit_id) or PricingRule(tenant_id=ctx.tenant.id, unit_id=unit_id)
    rule.weekday_price, rule.weekend_price, rule.currency = body.weekday_price, body.weekend_price, body.currency
    rule.seasonal_price_json = body.seasonal.model_dump(mode="json")
    return await persist(ctx.session, rule)


@router.post("/quote", response_model=QuoteOut, summary="Price a stay night-by-night")
async def quote(body: QuoteRequest, ctx: TenantContext = Depends(authorize("pricing:read"))):
    await get_or_404(ctx, Unit, body.unit_id, "Unit")
    stay = await quote_for_unit(ctx.session, ctx.tenant.id, body.unit_id, body.check_in, body.check_out)
    return QuoteOut(unit_id=body.unit_id, currency=stay.currency, total=stay.total,
                    nights=[NightPriceOut(night=n.night, day_type=n.day_type, base_price=n.base_price,
                                          applied_rules=n.applied_rules, price=n.price) for n in stay.nights])
