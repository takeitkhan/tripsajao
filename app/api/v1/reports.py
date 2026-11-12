from fastapi import APIRouter, Depends, Query

from app.core.deps import TenantContext, authorize
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/overview", summary="Business overview: bookings, money, occupancy, arrivals, partners",
            description="Everything the Overview page shows. Money is in the business's main booking currency. `days` is the period for the totals and the daily chart.")
async def overview(days: int = Query(30, ge=7, le=90), ctx: TenantContext = Depends(authorize("reports:read"))) -> dict:
    return await reports.overview(ctx.session, ctx.tenant, days)
