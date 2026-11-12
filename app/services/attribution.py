"""Short-code affiliate attribution: encrypted HTTP-only cookie  <->  partner."""
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import open_referral
from app.models import Partner

REF_HEADER = "X-Ref-Token"


def read_referral_token(request: Request) -> str | None:
    """Cookie first (same-site / proxied setups); header fallback for headless frontends that
    forward the cookie value from a server-side render or a cross-origin fetch."""
    return request.cookies.get(settings.referral_cookie_name) or request.headers.get(REF_HEADER)


async def resolve_partner(session: AsyncSession, tenant_id: UUID, request: Request) -> Partner | None:
    data = open_referral(read_referral_token(request), settings.referral_cookie_days * 86400)
    if not data or data.get("t") != str(tenant_id):          # cookie minted for another tenant -> ignore
        return None
    try:
        partner_id = UUID(data["p"])
    except (KeyError, ValueError):
        return None
    return (await session.execute(
        select(Partner).where(Partner.id == partner_id, Partner.tenant_id == tenant_id, Partner.is_active.is_(True))
    )).scalar_one_or_none()
