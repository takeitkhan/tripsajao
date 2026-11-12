from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import Package, TourEvent
from app.schemas.common import Page, Pagination
from app.schemas.tours import EventIn, EventOut, EventUpdate
from app.services.tours import slugify
from app.services.event_booking import seats_taken


async def _with_left(ctx, evs):
    taken = await seats_taken(ctx.session, ctx.tenant.id, [e.id for e in evs])
    for e in evs:
        e.seats_left = None if e.seats is None else max(e.seats - taken.get(e.id, 0), 0)
    return evs


router = APIRouter(prefix="/events", tags=["events"])


def _public(ctx: TenantContext) -> bool:
    return ctx.principal.kind == "api_client"      # a website only ever sees published events


@router.get("", response_model=Page[EventOut], summary="List events (websites get published ones only)")
async def list_events(status_: str | None = Query(None, alias="status", pattern="^(DRAFT|PUBLISHED|CLOSED)$"), upcoming: bool = Query(False, description="Only events that have not ended"),
                      package_id: UUID | None = None, pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("events:read"))):
    stmt = select(TourEvent).where(TourEvent.tenant_id == ctx.tenant.id)
    if _public(ctx):
        stmt = stmt.where(TourEvent.status == "PUBLISHED", TourEvent.ends_on >= date.today())
    elif status_:
        stmt = stmt.where(TourEvent.status == status_)
    if upcoming:
        stmt = stmt.where(TourEvent.ends_on >= date.today())
    if package_id:
        stmt = stmt.where(TourEvent.package_id == package_id)
    page = await paginate(ctx.session, stmt.order_by(TourEvent.starts_on, TourEvent.title), pg)
    page["items"] = await _with_left(ctx, list(page["items"]))
    return page


@router.get("/{slug}", response_model=EventOut, summary="One event by its slug")
async def one(slug: str, ctx: TenantContext = Depends(authorize("events:read"))):
    stmt = select(TourEvent).where(TourEvent.tenant_id == ctx.tenant.id, TourEvent.slug == slug)
    if _public(ctx):
        stmt = stmt.where(TourEvent.status == "PUBLISHED")
    ev = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Event not found")
    return (await _with_left(ctx, [ev]))[0]


@router.post("", response_model=EventOut, status_code=201, summary="Create an event by hand (or use a package to do it faster)")
async def create(body: EventIn, ctx: TenantContext = Depends(authorize("events:write"))):
    if body.package_id:
        await get_or_404(ctx, Package, body.package_id, "Package")
    ends = body.ends_on or body.starts_on
    if ends < body.starts_on:
        raise HTTPException(422, "The end date is before the start date")
    data = body.model_dump(mode="json", exclude={"slug", "ends_on", "starts_on"})
    ev = TourEvent(tenant_id=ctx.tenant.id, slug=body.slug or f"{slugify(body.title)}-{body.starts_on.isoformat()}", starts_on=body.starts_on, ends_on=ends,
                   published_at=datetime.now(timezone.utc) if body.status == "PUBLISHED" else None, **data)
    return await persist(ctx.session, ev, "An event with this web address (slug) already exists")


@router.patch("/{event_id}", response_model=EventOut, summary="Change an event, publish it, or close it")
async def update(event_id: UUID, body: EventUpdate, ctx: TenantContext = Depends(authorize("events:write"))):
    ev = await get_or_404(ctx, TourEvent, event_id, "Event")
    for k, v in body.model_dump(exclude_unset=True, mode="python").items():
        if v is None and k in ("itinerary", "inclusions", "exclusions", "trip_types", "other_transport", "health_rules", "warnings", "essentials", "photos", "payment_methods", "title", "slug", "starts_on", "ends_on", "price", "currency", "status"):
            continue
        if k in ("itinerary",):
            v = [d.model_dump() if hasattr(d, "model_dump") else d for d in v]
        setattr(ev, k, v)
    if ev.ends_on < ev.starts_on:
        raise HTTPException(422, "The end date is before the start date")
    if ev.status == "PUBLISHED" and ev.published_at is None:
        ev.published_at = datetime.now(timezone.utc)
    return await persist(ctx.session, ev, "An event with this web address (slug) already exists")


@router.delete("/{event_id}", status_code=204, summary="Delete an event")
async def delete(event_id: UUID, ctx: TenantContext = Depends(authorize("events:write"))):
    await ctx.session.delete(await get_or_404(ctx, TourEvent, event_id, "Event"))
