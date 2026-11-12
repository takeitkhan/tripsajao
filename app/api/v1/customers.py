from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text

from app.core.deps import TenantContext, authorize
from app.models import Customer
from app.schemas.common import Page, Pagination
from app.schemas.crm import (BulkTag, BulkTagResult, CustomerCreate, CustomerDetail, CustomerFilters, CustomerOut, CustomerUpdate, TagCount,
                             customer_filters)
from app.services import crm

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=Page[CustomerOut], summary="List customers (everyone who booked or wrote in), with filters")
async def list_customers(f: CustomerFilters = Depends(customer_filters), pg: Pagination = Depends(),
                         ctx: TenantContext = Depends(authorize("customers:read"))):
    items, total = await crm.list_customers(ctx.session, ctx.tenant, f, pg.limit, pg.offset)
    return {"items": items, "total": total, "limit": pg.limit, "offset": pg.offset}


@router.get("/tags", response_model=list[TagCount], summary="Tags in use and how many customers carry each")
async def tags(ctx: TenantContext = Depends(authorize("customers:read"))):
    rows = (await ctx.session.execute(text("SELECT t AS tag, count(*) AS n FROM customers c, jsonb_array_elements_text(c.tags) t "
                                           "WHERE c.tenant_id = :t GROUP BY t ORDER BY n DESC, t LIMIT 200"), {"t": ctx.tenant.id})).all()
    return [TagCount(tag=r.tag, customers=r.n) for r in rows]


@router.get("/export", summary="Download the filtered list as a CSV file (opens in Excel)")
async def export(f: CustomerFilters = Depends(customer_filters), ctx: TenantContext = Depends(authorize("customers:export"))):
    body = await crm.export_csv(ctx.session, ctx.tenant, f)
    return Response(body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="customers.csv"', "Cache-Control": "no-store"})


@router.post("", response_model=CustomerDetail, status_code=201, summary="Add a customer by hand")
async def create(body: CustomerCreate, ctx: TenantContext = Depends(authorize("customers:manage"))):
    await crm.sync_from_bookings(ctx.session, ctx.tenant.id)
    email = body.email.lower()
    exists = (await ctx.session.execute(text("SELECT 1 FROM customers WHERE tenant_id = :t AND email = :e"), {"t": ctx.tenant.id, "e": email})).first()
    if exists:
        raise HTTPException(409, "A customer with this email already exists")
    c = Customer(tenant_id=ctx.tenant.id, email=email, name=body.name.strip(), phone=(body.phone or "").strip() or None, tags=body.tags, notes=body.notes, source="MANUAL")
    ctx.session.add(c)
    await ctx.session.flush()
    return await crm.get_customer(ctx.session, ctx.tenant, c.id)


@router.post("/tags/apply", response_model=BulkTagResult, summary="Add or remove tags on many customers at once")
async def bulk_tag(body: BulkTag, ctx: TenantContext = Depends(authorize("customers:manage"))):
    if not body.add and not body.remove:
        raise HTTPException(422, "Give at least one tag to add or remove")
    ids = body.ids if body.ids else (await crm.matching_ids(ctx.session, ctx.tenant, body.filters or CustomerFilters()) if body.filters else None)
    if not ids:
        raise HTTPException(422, "Choose customers, or send filters")
    res = await ctx.session.execute(text("""
        UPDATE customers c SET updated_at = now(), tags = (
            SELECT coalesce(jsonb_agg(x ORDER BY x), '[]'::jsonb) FROM (
              SELECT DISTINCT x FROM (SELECT jsonb_array_elements_text(c.tags) AS x UNION SELECT unnest(CAST(:add AS text[]))) u
              WHERE x <> ALL (CAST(:rem AS text[]))) y)
        WHERE c.tenant_id = :t AND c.id = ANY(CAST(:ids AS uuid[]))"""), {"t": ctx.tenant.id, "add": body.add, "rem": body.remove, "ids": [str(i) for i in ids]})
    return BulkTagResult(changed=res.rowcount)


@router.get("/{customer_id}", response_model=CustomerDetail, summary="One customer with every booking")
async def one(customer_id: UUID, ctx: TenantContext = Depends(authorize("customers:read"))):
    c = await crm.get_customer(ctx.session, ctx.tenant, customer_id)
    if c is None:
        raise HTTPException(404, "Customer not found")
    return c


@router.patch("/{customer_id}", response_model=CustomerDetail, summary="Change name, phone, tags or notes")
async def update(customer_id: UUID, body: CustomerUpdate, ctx: TenantContext = Depends(authorize("customers:manage"))):
    c = await ctx.session.get(Customer, customer_id)
    if c is None or c.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "Customer not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        c.name = data["name"].strip()
    if "phone" in data:
        c.phone = (data["phone"] or "").strip() or None
    if "tags" in data and data["tags"] is not None:
        c.tags = data["tags"]
    if "notes" in data:
        c.notes = (data["notes"] or "").strip() or None
    await ctx.session.flush()
    return await crm.get_customer(ctx.session, ctx.tenant, c.id)
