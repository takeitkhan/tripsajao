from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import Text, cast, func, or_, select, text

from app.core.deps import TenantContext, authorize, get_or_404, persist
from app.models import MediaAsset
from app.models.enums import MediaKind, MediaSource
from app.schemas.common import Message, Page, Pagination
from app.schemas.media import MediaLink, MediaOut, MediaSummary, MediaUpdate, MediaUsage
from app.services import media as svc
from app.services.limits import limit_of

router = APIRouter(prefix="/media", tags=["media"])


def _tags(raw: str | None) -> list[str]:
    out: list[str] = []
    for t in (raw or "").split(","):
        t = t.strip()[:40]
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out[:20]


@router.get("", response_model=Page[MediaOut], summary="List photos and videos")
async def list_media(kind: MediaKind | None = None, q: str | None = Query(None, max_length=100, description="Search title, file name or tag"),
                     tag: str | None = Query(None, max_length=40), pg: Pagination = Depends(),
                     ctx: TenantContext = Depends(authorize("media:read"))):
    stmt = select(MediaAsset).where(MediaAsset.tenant_id == ctx.tenant.id)
    if kind:
        stmt = stmt.where(MediaAsset.kind == kind)
    if tag:
        stmt = stmt.where(MediaAsset.tags.contains([tag]))
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        stmt = stmt.where(or_(MediaAsset.title.ilike(like, escape="\\"), MediaAsset.original_name.ilike(like, escape="\\"),
                              MediaAsset.alt_text.ilike(like, escape="\\"), cast(MediaAsset.tags, Text).ilike(like, escape="\\")))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(MediaAsset.created_at.desc()).limit(pg.limit).offset(pg.offset))).scalars().all()
    return {"items": [svc.describe(a) for a in rows], "total": total, "limit": pg.limit, "offset": pg.offset}


@router.get("/summary", response_model=MediaSummary, summary="Storage used, limits and accepted formats")
async def summary(ctx: TenantContext = Depends(authorize("media:read"))):
    rows = dict((await ctx.session.execute(select(MediaAsset.kind, func.count()).where(MediaAsset.tenant_id == ctx.tenant.id).group_by(MediaAsset.kind))).all())
    lim = svc.limits()
    return MediaSummary(images=rows.get(MediaKind.IMAGE, 0), videos=rows.get(MediaKind.VIDEO, 0), used_bytes=await svc.tenant_usage(ctx.session, ctx.tenant.id),
                        quota_bytes=int(limit_of(ctx.tenant, 'media_quota_mb')) * 1024 * 1024, max_image_bytes=lim["image"], max_video_bytes=lim["video"], allowed=svc.ALLOWED)


@router.get("/tags", response_model=list[str], summary="Tags in use")
async def tags(ctx: TenantContext = Depends(authorize("media:read"))):
    rows = await ctx.session.execute(text("SELECT DISTINCT t FROM media_assets, jsonb_array_elements_text(tags) AS t "
                                          "WHERE tenant_id = :tid ORDER BY t LIMIT 200"), {"tid": ctx.tenant.id})
    return [r[0] for r in rows]


@router.post("", response_model=MediaOut, status_code=201, summary="Upload a photo or video",
             description="Send as `multipart/form-data` with a `file` field (JPG, PNG, WEBP, GIF, MP4, MOV or WEBM). Optional: `title`, `alt_text`, `tags` (comma separated).")
async def upload(file: UploadFile = File(...), title: str | None = Form(None, max_length=200), alt_text: str | None = Form(None, max_length=300),
                 tags: str | None = Form(None, max_length=500), ctx: TenantContext = Depends(authorize("media:write"))):
    asset = await svc.store_upload(ctx.session, ctx.tenant, ctx.principal.user_id, file, title, alt_text, _tags(tags))
    return svc.describe(asset)


@router.post("/link", response_model=MediaOut, status_code=201, summary="Add a video by link (YouTube, Vimeo or a direct file link)")
async def add_link(body: MediaLink, ctx: TenantContext = Depends(authorize("media:write"))):
    url, provider, _embed, _thumb = svc.parse_link(body.url)
    title = body.title or {"youtube": "YouTube video", "vimeo": "Vimeo video"}.get(provider) or url.rsplit("/", 1)[-1][:120]
    asset = await persist(ctx.session, MediaAsset(tenant_id=ctx.tenant.id, kind=MediaKind.VIDEO, source=MediaSource.EXTERNAL, title=title,
                                                  alt_text=body.alt_text, tags=body.tags, external_url=url, created_by=ctx.principal.user_id))
    return svc.describe(asset)


@router.get("/{media_id}", response_model=MediaOut, summary="Get one photo or video")
async def get_one(media_id: UUID, ctx: TenantContext = Depends(authorize("media:read"))):
    return svc.describe(await get_or_404(ctx, MediaAsset, media_id, "Media"))


@router.patch("/{media_id}", response_model=MediaOut, summary="Rename, describe or tag")
async def update(media_id: UUID, body: MediaUpdate, ctx: TenantContext = Depends(authorize("media:write"))):
    a = await get_or_404(ctx, MediaAsset, media_id, "Media")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "alt_text":
            setattr(a, k, v)
    await ctx.session.flush()
    return svc.describe(a)


@router.get("/{media_id}/usage", response_model=MediaUsage, summary="Where this file is used")
async def usage(media_id: UUID, ctx: TenantContext = Depends(authorize("media:read"))):
    a = await get_or_404(ctx, MediaAsset, media_id, "Media")
    places = await svc.find_usage(ctx.session, ctx.tenant, a)
    return {"count": len(places), "places": places}


@router.delete("/{media_id}", status_code=204, summary="Delete a file",
               responses={409: {"model": Message, "description": "The file is still used. Repeat with `force=true` to delete anyway."}})
async def delete(media_id: UUID, force: bool = False, ctx: TenantContext = Depends(authorize("media:write"))):
    a = await get_or_404(ctx, MediaAsset, media_id, "Media")
    if not force and (places := await svc.find_usage(ctx.session, ctx.tenant, a)):
        raise HTTPException(409, f"This file is used in {len(places)} place{'s' if len(places) != 1 else ''}. Remove it there first, or delete anyway.")
    await ctx.session.delete(a)
    await ctx.session.flush()
    svc.remove_files(a)
