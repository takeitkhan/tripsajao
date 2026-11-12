from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import Budget, Package, TourEvent
from app.schemas.cms import CompanyInfo
from app.schemas.common import Page, Pagination
from app.schemas.tours import BudgetIn, BudgetOut, BudgetRow, BudgetUpdate
from app.services.tours import compute

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _out(b: Budget) -> BudgetOut:
    calc = compute(b.lines, b.people, b.margin_percent)
    return BudgetOut(id=b.id, title=b.title, client_name=b.client_name, client_phone=b.client_phone, event_id=b.event_id, package_id=b.package_id,
                     people=b.people, currency=b.currency, margin_percent=b.margin_percent, notes=b.notes, status=b.status,
                     created_at=b.created_at, updated_at=b.updated_at, **calc)


async def _check_links(ctx: TenantContext, event_id, package_id) -> None:
    if event_id:
        await get_or_404(ctx, TourEvent, event_id, "Event")
    if package_id:
        await get_or_404(ctx, Package, package_id, "Package")


def _store(b: Budget) -> None:
    c = compute(b.lines, b.people, b.margin_percent)
    b.cost_total, b.sell_total = c["cost_total"], c["sell_total"]


@router.get("", response_model=Page[BudgetRow], summary="Saved budgets")
async def list_budgets(q: str | None = Query(None, max_length=100), status_: str | None = Query(None, alias="status", pattern="^(DRAFT|SENT|WON|LOST)$"),
                       pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("budgets:read"))):
    stmt = select(Budget).where(Budget.tenant_id == ctx.tenant.id)
    if status_:
        stmt = stmt.where(Budget.status == status_)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Budget.title.ilike(like), Budget.client_name.ilike(like)))
    return await paginate(ctx.session, stmt.order_by(Budget.updated_at.desc()), pg)


@router.post("", response_model=BudgetOut, status_code=201, summary="Save a budget")
async def create(body: BudgetIn, ctx: TenantContext = Depends(authorize("budgets:write"))):
    await _check_links(ctx, body.event_id, body.package_id)
    data = body.model_dump(mode="json")
    b = Budget(tenant_id=ctx.tenant.id, **data)
    _store(b)
    return _out(await persist(ctx.session, b))


@router.get("/company", response_model=CompanyInfo, summary="Company name, logo and address for the printed quotation")
async def company(ctx: TenantContext = Depends(authorize("budgets:read"))):
    c = CompanyInfo.model_validate((ctx.tenant.settings_json or {}).get("company", {}))
    return c.model_copy(update={"name": c.name or ctx.tenant.name, "social": {}})


@router.get("/{budget_id}", response_model=BudgetOut, summary="One budget with worked-out totals")
async def one(budget_id: UUID, ctx: TenantContext = Depends(authorize("budgets:read"))):
    return _out(await get_or_404(ctx, Budget, budget_id, "Budget"))


@router.patch("/{budget_id}", response_model=BudgetOut, summary="Change a budget; totals are worked out again")
async def update(budget_id: UUID, body: BudgetUpdate, ctx: TenantContext = Depends(authorize("budgets:write"))):
    b = await get_or_404(ctx, Budget, budget_id, "Budget")
    data = body.model_dump(exclude_unset=True, mode="json")
    await _check_links(ctx, data.get("event_id"), data.get("package_id"))
    for k, v in data.items():
        if v is None and k in ("title", "people", "currency", "lines", "margin_percent", "status"):
            continue
        setattr(b, k, v)
    _store(b)
    return _out(await persist(ctx.session, b))


@router.post("/{budget_id}/copy", response_model=BudgetOut, status_code=201, summary="Copy a budget to start a new one from it")
async def copy(budget_id: UUID, ctx: TenantContext = Depends(authorize("budgets:write"))):
    b = await get_or_404(ctx, Budget, budget_id, "Budget")
    n = Budget(tenant_id=ctx.tenant.id, title=f"{b.title} (copy)"[:300], client_name=b.client_name, client_phone=b.client_phone, event_id=b.event_id,
               package_id=b.package_id, people=b.people, currency=b.currency, lines=b.lines, margin_percent=b.margin_percent, notes=b.notes, status="DRAFT")
    _store(n)
    return _out(await persist(ctx.session, n))


@router.delete("/{budget_id}", status_code=204, summary="Delete a budget")
async def delete(budget_id: UUID, ctx: TenantContext = Depends(authorize("budgets:write"))):
    await ctx.session.delete(await get_or_404(ctx, Budget, budget_id, "Budget"))
