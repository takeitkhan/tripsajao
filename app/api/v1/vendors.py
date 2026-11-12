from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import Vendor, VendorRate
from app.schemas.common import Page, Pagination
from app.schemas.tours import RateFound, RateIn, RateOut, RateUpdate, VendorDetail, VendorIn, VendorOut, VendorUpdate

router = APIRouter(tags=["vendors"])


def _out(v: Vendor, n: int) -> VendorOut:
    return VendorOut(id=v.id, category=v.category, name=v.name, location=v.location, phone=v.phone, email=v.email, address=v.address, notes=v.notes,
                     is_active=v.is_active, rate_count=n)


@router.get("/vendors", response_model=Page[VendorOut], summary="List vendors, by place and kind")
async def list_vendors(q: str | None = Query(None, max_length=100), category: str | None = Query(None, max_length=14), location: str | None = Query(None, max_length=200),
                       active: bool | None = None, pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("vendors:read"))):
    stmt = select(Vendor).where(Vendor.tenant_id == ctx.tenant.id)
    if category:
        stmt = stmt.where(Vendor.category == category)
    if location:
        stmt = stmt.where(func.lower(Vendor.location) == location.strip().lower())
    if active is not None:
        stmt = stmt.where(Vendor.is_active.is_(active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Vendor.name.ilike(like), Vendor.phone.ilike(like), Vendor.location.ilike(like)))
    page = await paginate(ctx.session, stmt.order_by(Vendor.location, Vendor.category, Vendor.name), pg)
    ids = [v.id for v in page["items"]]
    counts = dict((await ctx.session.execute(select(VendorRate.vendor_id, func.count()).where(VendorRate.vendor_id.in_(ids)).group_by(VendorRate.vendor_id))).all()) if ids else {}
    page["items"] = [_out(v, counts.get(v.id, 0)) for v in page["items"]]
    return page


@router.get("/vendors/locations", response_model=list[str], summary="Places that have vendors")
async def locations(ctx: TenantContext = Depends(authorize("vendors:read"))):
    rows = (await ctx.session.execute(select(Vendor.location).where(Vendor.tenant_id == ctx.tenant.id).distinct().order_by(Vendor.location))).scalars().all()
    return list(rows)


@router.post("/vendors", response_model=VendorOut, status_code=201, summary="Add a vendor")
async def create(body: VendorIn, ctx: TenantContext = Depends(authorize("vendors:write"))):
    v = await persist(ctx.session, Vendor(tenant_id=ctx.tenant.id, **body.model_dump()))
    return _out(v, 0)


@router.get("/vendors/{vendor_id}", response_model=VendorDetail, summary="One vendor with every rate")
async def one(vendor_id: UUID, ctx: TenantContext = Depends(authorize("vendors:read"))):
    v = await get_or_404(ctx, Vendor, vendor_id, "Vendor")
    rates = (await ctx.session.execute(select(VendorRate).where(VendorRate.vendor_id == v.id).order_by(VendorRate.item))).scalars().all()
    return VendorDetail(**_out(v, len(rates)).model_dump(), rates=[RateOut.model_validate(r) for r in rates])


@router.patch("/vendors/{vendor_id}", response_model=VendorOut, summary="Change a vendor")
async def update(vendor_id: UUID, body: VendorUpdate, ctx: TenantContext = Depends(authorize("vendors:write"))):
    v = await get_or_404(ctx, Vendor, vendor_id, "Vendor")
    for k, val in body.model_dump(exclude_unset=True).items():
        if val is None and k in ("category", "name", "location", "is_active"):
            continue
        setattr(v, k, val)
    await ctx.session.flush()
    n = (await ctx.session.execute(select(func.count()).select_from(VendorRate).where(VendorRate.vendor_id == v.id))).scalar_one()
    return _out(v, n)


@router.delete("/vendors/{vendor_id}", status_code=204, summary="Delete a vendor and its rates")
async def delete(vendor_id: UUID, ctx: TenantContext = Depends(authorize("vendors:write"))):
    await ctx.session.delete(await get_or_404(ctx, Vendor, vendor_id, "Vendor"))


@router.post("/vendors/{vendor_id}/rates", response_model=RateOut, status_code=201, summary="Add a rate to a vendor")
async def add_rate(vendor_id: UUID, body: RateIn, ctx: TenantContext = Depends(authorize("vendors:write"))):
    v = await get_or_404(ctx, Vendor, vendor_id, "Vendor")
    return await persist(ctx.session, VendorRate(tenant_id=ctx.tenant.id, vendor_id=v.id, **body.model_dump()))


@router.get("/rates", response_model=Page[RateFound], summary="Search rates across vendors, by place and kind (used by the budget calculator)")
async def search_rates(q: str | None = Query(None, max_length=100), category: str | None = Query(None, max_length=14), location: str | None = Query(None, max_length=200),
                       pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("vendors:read"))):
    stmt = (select(VendorRate, Vendor.name, Vendor.category, Vendor.location).join(Vendor, Vendor.id == VendorRate.vendor_id)
            .where(VendorRate.tenant_id == ctx.tenant.id, Vendor.is_active.is_(True)))
    if category:
        stmt = stmt.where(Vendor.category == category)
    if location:
        stmt = stmt.where(func.lower(Vendor.location) == location.strip().lower())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(VendorRate.item.ilike(like), Vendor.name.ilike(like)))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(Vendor.location, Vendor.name, VendorRate.item).limit(pg.limit).offset(pg.offset))).all()
    items = [RateFound(**RateOut.model_validate(r).model_dump(), vendor_name=n, category=c, location=loc) for r, n, c, loc in rows]
    return {"items": items, "total": total, "limit": pg.limit, "offset": pg.offset}


@router.patch("/rates/{rate_id}", response_model=RateOut, summary="Change a rate")
async def update_rate(rate_id: UUID, body: RateUpdate, ctx: TenantContext = Depends(authorize("vendors:write"))):
    r = await get_or_404(ctx, VendorRate, rate_id, "Rate")
    for k, val in body.model_dump(exclude_unset=True).items():
        if val is None and k in ("item", "unit", "price", "currency"):
            continue
        setattr(r, k, val)
    return await persist(ctx.session, r)


@router.delete("/rates/{rate_id}", status_code=204, summary="Delete a rate")
async def delete_rate(rate_id: UUID, ctx: TenantContext = Depends(authorize("vendors:write"))):
    await ctx.session.delete(await get_or_404(ctx, VendorRate, rate_id, "Rate"))
