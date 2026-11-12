from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.services.limits import enforce
from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import Property, PropertyType, Unit
from app.schemas.common import Page, Pagination
from app.schemas.inventory import (FACILITY_PRESETS, Facility, PropertyCreate, PropertyOut, PropertyUpdate, UnitCreate,
                                   UnitOut, UnitUpdate, unit_type_allowed)

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/facility-presets", response_model=list[Facility], summary="Suggested amenities with icon codes")
async def facility_presets(ctx: TenantContext = Depends(authorize("properties:read"))):
    return FACILITY_PRESETS


@router.post("", response_model=PropertyOut, status_code=201, summary="Create property")
async def create_property(body: PropertyCreate, ctx: TenantContext = Depends(authorize("properties:write"))):
    await enforce(ctx, "max_properties", Property)
    prop = Property(tenant_id=ctx.tenant.id, type=body.type, name=body.name, slug=body.slug, location=body.location,
                    metadata_json=body.metadata.model_dump(mode="json"))
    return await persist(ctx.session, prop, "A property with this slug already exists")


@router.get("", response_model=Page[PropertyOut], summary="List properties")
async def list_properties(type: PropertyType | None = None, include_inactive: bool = False,
                          pg: Pagination = Depends(),
                          ctx: TenantContext = Depends(authorize("properties:read"))):
    stmt = select(Property).where(Property.tenant_id == ctx.tenant.id).order_by(Property.name)
    if type:
        stmt = stmt.where(Property.type == type)
    if not (include_inactive and ctx.principal.kind != "api_client"):
        stmt = stmt.where(Property.is_active.is_(True))
    return await paginate(ctx.session, stmt, pg)


@router.get("/units/{unit_id}", response_model=UnitOut, summary="Get unit")
async def get_unit(unit_id: UUID, ctx: TenantContext = Depends(authorize("properties:read"))):
    return await get_or_404(ctx, Unit, unit_id, "Unit")


@router.patch("/units/{unit_id}", response_model=UnitOut, summary="Update unit (facilities, layout, maintenance status)")
async def update_unit(unit_id: UUID, body: UnitUpdate, ctx: TenantContext = Depends(authorize("properties:write"))):
    unit = await get_or_404(ctx, Unit, unit_id, "Unit")
    data = body.model_dump(exclude_unset=True, mode="json")
    mapping = {"facilities": "facilities_json", "media": "media_json", "layout": "layout_json"}
    for k, v in data.items():
        setattr(unit, mapping.get(k, k), v)
    return await persist(ctx.session, unit, "Unit name already exists in this property")


@router.delete("/units/{unit_id}", status_code=204, summary="Deactivate unit")
async def delete_unit(unit_id: UUID, ctx: TenantContext = Depends(authorize("properties:write"))):
    unit = await get_or_404(ctx, Unit, unit_id, "Unit")
    unit.is_active = False        # soft delete keeps booking history intact
    await ctx.session.flush()


@router.get("/{property_id}", response_model=PropertyOut, summary="Get property")
async def get_property(property_id: UUID, ctx: TenantContext = Depends(authorize("properties:read"))):
    return await get_or_404(ctx, Property, property_id, "Property")


@router.patch("/{property_id}", response_model=PropertyOut, summary="Update property")
async def update_property(property_id: UUID, body: PropertyUpdate,
                          ctx: TenantContext = Depends(authorize("properties:write"))):
    prop = await get_or_404(ctx, Property, property_id, "Property")
    for k, v in body.model_dump(exclude_unset=True, mode="json").items():
        setattr(prop, "metadata_json" if k == "metadata" else k, v)
    return await persist(ctx.session, prop, "A property with this slug already exists")


@router.delete("/{property_id}", status_code=204, summary="Deactivate property")
async def delete_property(property_id: UUID, ctx: TenantContext = Depends(authorize("properties:write"))):
    prop = await get_or_404(ctx, Property, property_id, "Property")
    prop.is_active = False
    await ctx.session.flush()


@router.post("/{property_id}/units", response_model=UnitOut, status_code=201, summary="Create unit / cabin")
async def create_unit(property_id: UUID, body: UnitCreate, ctx: TenantContext = Depends(authorize("properties:write"))):
    prop = await get_or_404(ctx, Property, property_id, "Property")
    await enforce(ctx, "max_units", Unit)
    if not unit_type_allowed(prop.type, body.type):
        raise HTTPException(422, f"Unit type {body.type.value} is not valid for a {prop.type.value}")
    unit = Unit(tenant_id=ctx.tenant.id, property_id=prop.id, unit_name=body.unit_name, type=body.type,
                capacity=body.capacity, facilities_json=[f.model_dump(mode="json") for f in body.facilities],
                media_json=[m.model_dump(mode="json") for m in body.media], layout_json=body.layout)
    return await persist(ctx.session, unit, "Unit name already exists in this property")


@router.get("/{property_id}/units", response_model=Page[UnitOut], summary="List units of a property")
async def list_units(property_id: UUID, pg: Pagination = Depends(),
                     ctx: TenantContext = Depends(authorize("properties:read"))):
    await get_or_404(ctx, Property, property_id, "Property")
    stmt = select(Unit).where(Unit.tenant_id == ctx.tenant.id, Unit.property_id == property_id,
                              Unit.is_active.is_(True)).order_by(Unit.unit_name)
    return await paginate(ctx.session, stmt, pg)
