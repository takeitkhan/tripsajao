import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select

from app.core.deps import TenantContext, authorize, get_or_404, paginate, persist
from app.models import CMSContent, CMSStatus, CMSType
from app.schemas.cms import PAYLOAD_MODELS, CMSCreate, CMSOut, CMSUpdate, CompanyInfo
from app.schemas.common import Page, Pagination

router = APIRouter(prefix="/cms", tags=["cms"])
ContentPath = Literal["blog", "event", "gallery", "page", "announcement"]


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:150] or "untitled"


def _validate_payload(ctype: CMSType, payload: dict) -> dict:
    try:
        return PAYLOAD_MODELS[ctype].model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors(include_url=False, include_context=False)) from exc


def _public_only(ctx: TenantContext) -> bool:
    return ctx.principal.kind == "api_client"          # websites only ever see published content


@router.get("/company", response_model=CompanyInfo, summary="Company info & settings")
async def get_company(ctx: TenantContext = Depends(authorize("cms:read"))):
    return CompanyInfo.model_validate(ctx.tenant.settings_json.get("company", {}))


@router.put("/company", response_model=CompanyInfo, summary="Update company info")
async def put_company(body: CompanyInfo, ctx: TenantContext = Depends(authorize("cms:write"))):
    ctx.tenant.settings_json = {**ctx.tenant.settings_json, "company": body.model_dump(mode="json")}   # reassign -> dirty
    await ctx.session.flush()
    return body


@router.get("/{content_type}", response_model=Page[CMSOut], summary="List content (blogs, events, galleries, pages, announcements)")
async def list_content(content_type: ContentPath, status_: CMSStatus | None = Query(None, alias="status"),
                       pg: Pagination = Depends(), ctx: TenantContext = Depends(authorize("cms:read"))):
    stmt = select(CMSContent).where(CMSContent.tenant_id == ctx.tenant.id,
                                    CMSContent.content_type == CMSType(content_type.upper()))
    if _public_only(ctx):
        stmt = stmt.where(CMSContent.status == CMSStatus.PUBLISHED)
    elif status_:
        stmt = stmt.where(CMSContent.status == status_)
    return await paginate(ctx.session, stmt.order_by(CMSContent.published_at.desc().nullslast(), CMSContent.created_at.desc()), pg)


@router.get("/{content_type}/{slug}", response_model=CMSOut, summary="Get one content item by slug")
async def get_content(content_type: ContentPath, slug: str, ctx: TenantContext = Depends(authorize("cms:read"))):
    stmt = select(CMSContent).where(CMSContent.tenant_id == ctx.tenant.id, CMSContent.slug == slug,
                                    CMSContent.content_type == CMSType(content_type.upper()))
    if _public_only(ctx):
        stmt = stmt.where(CMSContent.status == CMSStatus.PUBLISHED)
    item = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Content not found")
    return item


@router.post("/{content_type}", response_model=CMSOut, status_code=201, summary="Create content")
async def create_content(content_type: ContentPath, body: CMSCreate, ctx: TenantContext = Depends(authorize("cms:write"))):
    ctype = CMSType(content_type.upper())
    item = CMSContent(tenant_id=ctx.tenant.id, content_type=ctype, title=body.title, slug=body.slug or _slugify(body.title),
                      status=body.status, payload_json=_validate_payload(ctype, body.payload),
                      published_at=datetime.now(timezone.utc) if body.status == CMSStatus.PUBLISHED else None)
    return await persist(ctx.session, item, "Slug already exists for this content type")


@router.put("/{content_type}/{item_id}", response_model=CMSOut, summary="Update content")
async def update_content(content_type: ContentPath, item_id: UUID, body: CMSUpdate,
                         ctx: TenantContext = Depends(authorize("cms:write"))):
    item = await get_or_404(ctx, CMSContent, item_id, "Content")
    if item.content_type.value != content_type.upper():
        raise HTTPException(404, "Content not found")
    data = body.model_dump(exclude_unset=True)
    if "payload" in data:
        item.payload_json = _validate_payload(item.content_type, data.pop("payload"))
    for k, v in data.items():
        setattr(item, k, v)
    if item.status == CMSStatus.PUBLISHED and item.published_at is None:
        item.published_at = datetime.now(timezone.utc)
    return await persist(ctx.session, item, "Slug already exists for this content type")


@router.delete("/{content_type}/{item_id}", status_code=204, summary="Delete content")
async def delete_content(content_type: ContentPath, item_id: UUID, ctx: TenantContext = Depends(authorize("cms:write"))):
    item = await get_or_404(ctx, CMSContent, item_id, "Content")
    if item.content_type.value != content_type.upper():
        raise HTTPException(404, "Content not found")
    await ctx.session.delete(item)
