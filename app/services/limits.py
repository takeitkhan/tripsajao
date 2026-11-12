"""Per-tenant limits set by the super admin (tenants.limits_json). A missing key means "no limit"."""
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings

LABELS = {"max_properties": "properties", "max_units": "rooms and cabins", "max_partners": "partners"}
KEYS = ("max_properties", "max_units", "max_partners", "media_quota_mb")


def limit_of(tenant, key: str):
    v = (tenant.limits_json or {}).get(key)
    if key == "media_quota_mb" and v is None:
        return settings.media_quota_mb
    return v


async def enforce(ctx, key: str, model, *, adding: int = 1) -> None:
    lim = limit_of(ctx.tenant, key)
    if lim is None:
        return
    used = (await ctx.session.execute(select(func.count()).select_from(model).where(model.tenant_id == ctx.tenant.id))).scalar_one()
    if used + adding > lim:
        raise HTTPException(403, f"Your plan allows up to {lim} {LABELS[key]} and you have {used}. Ask your account manager to raise the limit.")
