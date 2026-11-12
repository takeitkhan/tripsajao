from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import Package, TourEvent
from app.schemas.common import Page, Pagination
from app.schemas.tours import EventFromPackage, EventOut, PackageIn, PackageOut, PackageUpdate
from app.services.tours import last_day, slugify
from datetime import datetime, timezone

router = APIRouter(prefix="/packages", tags=["packages"])
LISTY = ("itinerary", "inclusions", "exclusions", "trip_types", "other_transport", "health_rules", "warnings", "essentials", "photos")


def _public(ctx: TenantContext) -> bool:
    return ctx.principal.kind == "api_client"      # a website only ever sees published packages


@router.get("", response_model=Page[PackageOut], summary="List packages (websites get published ones only)")
async def list_packages(q: str | None = Query(None, max_length=100), published: bool | None = None, pg: Pagination = Depends(),
                        ctx: TenantContext = Depends(authorize("events:read"))):
    stmt = select(Package).where(Package.tenant_id == ctx.tenant.id)
    if _public(ctx):
        stmt = stmt.where(Package.is_published.is_(True))
    elif published is not None:
        stmt = stmt.where(Package.is_published.is_(published))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Package.title.ilike(like), Package.location.ilike(like)))
    return await paginate(ctx.session, stmt.order_by(Package.starting_price, Package.title), pg)


@router.get("/{slug}", response_model=PackageOut, summary="One package by its slug")
async def one(slug: str, ctx: TenantContext = Depends(authorize("events:read"))):
    stmt = select(Package).where(Package.tenant_id == ctx.tenant.id, Package.slug == slug)
    if _public(ctx):
        stmt = stmt.where(Package.is_published.is_(True))
    p = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Package not found")
    return p


@router.post("", response_model=PackageOut, status_code=201, summary="Create a package")
async def create(body: PackageIn, ctx: TenantContext = Depends(authorize("events:write"))):
    data = body.model_dump(mode="json")
    data["slug"] = data["slug"] or slugify(body.title)
    return await persist(ctx.session, Package(tenant_id=ctx.tenant.id, **data), "A package with this web address (slug) already exists")


@router.patch("/{package_id}", response_model=PackageOut, summary="Change a package")
async def update(package_id: UUID, body: PackageUpdate, ctx: TenantContext = Depends(authorize("events:write"))):
    p = await get_or_404(ctx, Package, package_id, "Package")
    for k, v in body.model_dump(exclude_unset=True, mode="json").items():
        if v is None and k in LISTY + ("title", "slug", "duration_days", "starting_price", "currency", "is_published"):
            continue
        setattr(p, k, v)
    return await persist(ctx.session, p, "A package with this web address (slug) already exists")


@router.delete("/{package_id}", status_code=204, summary="Delete a package (events already made from it stay)")
async def delete(package_id: UUID, ctx: TenantContext = Depends(authorize("events:write"))):
    await ctx.session.delete(await get_or_404(ctx, Package, package_id, "Package"))


@router.post("/{package_id}/events", response_model=EventOut, status_code=201, summary="Publish an event from a package")
async def make_event(package_id: UUID, body: EventFromPackage, ctx: TenantContext = Depends(authorize("events:write"))):
    """Copies the package's itinerary, inclusions, price and cover into a new dated event. Only the date is needed."""
    p = await get_or_404(ctx, Package, package_id, "Package")
    ends = body.ends_on or last_day(body.starts_on, p.duration_days)
    if ends < body.starts_on:
        raise HTTPException(422, "The end date is before the start date")
    title = (body.title or p.title).strip()
    base = f"{slugify(title)}-{body.starts_on.isoformat()}"
    taken = set((await ctx.session.execute(select(TourEvent.slug).where(TourEvent.tenant_id == ctx.tenant.id, TourEvent.slug.like(base + "%")))).scalars())
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    ev = TourEvent(tenant_id=ctx.tenant.id, package_id=p.id, slug=slug, title=title, summary=p.summary, description=p.description, location=p.location,
                   starts_on=body.starts_on, ends_on=ends, price=body.price if body.price is not None else p.starting_price, currency=p.currency,
                   seats=body.seats, itinerary=p.itinerary, inclusions=p.inclusions, exclusions=p.exclusions, cover_image=p.cover_image,
                   pickup_location=p.pickup_location, accommodation=p.accommodation, trip_types=p.trip_types, bus_type=p.bus_type, other_transport=p.other_transport,
                   health_rules=p.health_rules, warnings=p.warnings, essentials=p.essentials, photos=body.photos if body.photos is not None else p.photos,
                   payment_methods=body.payment_methods,
                   status="PUBLISHED" if body.publish else "DRAFT", published_at=datetime.now(timezone.utc) if body.publish else None)
    return await persist(ctx.session, ev)
