import json
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.deps import TenantContext, authorize, get_or_404
from app.core.redis import get_redis
from app.models import Property
from app.schemas.visual import VisualLayout
from app.services.events import channel
from app.services.visual import build_layout

router = APIRouter(prefix="/dashboard/visual", tags=["dashboard"])


@router.get("/stream", summary="Server-Sent Events: live unit status changes for this tenant")
async def stream(request: Request, ctx: TenantContext = Depends(authorize("dashboard:read"))):
    ch = channel(ctx.tenant.id)
    await ctx.session.close()          # don't pin a DB connection for the lifetime of the stream

    async def gen():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(ch)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                yield f"data: {msg['data']}\n\n" if msg else ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(ch)
            await pubsub.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{property_id}", response_model=VisualLayout,
            summary="Resort building grid or houseboat hull layout with live unit status")
async def visual_layout(property_id: UUID, check_in: date | None = Query(None), check_out: date | None = Query(None),
                        ctx: TenantContext = Depends(authorize("dashboard:read"))):
    prop = await get_or_404(ctx, Property, property_id, "Property")
    today = datetime.now(ZoneInfo(ctx.tenant.settings_json.get("timezone", "UTC"))).date()
    start = check_in or today
    end = check_out or start + timedelta(days=1)
    if end <= start:
        raise HTTPException(422, "check_out must be after check_in")
    return await build_layout(ctx.session, prop, start, end)
