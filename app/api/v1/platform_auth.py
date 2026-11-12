from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.core.db import PlatformSession
from app.core.platform_deps import PlatformCtx, get_platform_ctx
from app.core.redis import get_redis
from app.core.security import DUMMY_HASH, create_token, decode_token, verify_password
from app.models import PlatformAdmin
from app.schemas.platform import PAdmin, PLogin, PRefresh, PTokens
from app.services.platform import audit, client_ip

router = APIRouter(prefix="/platform/auth", tags=["platform"], include_in_schema=False)
ACCESS_MIN, REFRESH_HOURS = 15, 12
MAX_FAILS, WINDOW = 5, 900


async def _issue(admin: PlatformAdmin) -> PTokens:
    access, _ = create_token(sub=str(admin.id), tenant_id="platform", principal="platform", typ="p_access", expires=timedelta(minutes=ACCESS_MIN))
    refresh, jti = create_token(sub=str(admin.id), tenant_id="platform", principal="platform", typ="p_refresh", expires=timedelta(hours=REFRESH_HOURS))
    await get_redis().set(f"prefresh:{jti}", str(admin.id), ex=REFRESH_HOURS * 3600)
    return PTokens(access_token=access, refresh_token=refresh, expires_in=ACCESS_MIN * 60, admin=PAdmin.model_validate(admin))


@router.post("/login", response_model=PTokens)
async def login(body: PLogin, request: Request):
    redis, ip = get_redis(), client_ip(request) or "?"
    email = body.email.lower()
    keys = (f"ploginfail:{email}", f"ploginip:{ip}")
    if int(await redis.get(keys[0]) or 0) >= MAX_FAILS or int(await redis.get(keys[1]) or 0) >= MAX_FAILS * 4:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait 15 minutes and try again.")
    async with PlatformSession() as s:
        admin = (await s.execute(select(PlatformAdmin).where(PlatformAdmin.email == email, PlatformAdmin.is_active.is_(True)))).scalar_one_or_none()
        ok = verify_password(admin.password_hash if admin else DUMMY_HASH, body.password) and admin is not None
        if not ok:
            pipe = redis.pipeline()
            for k in keys:
                pipe.incr(k); pipe.expire(k, WINDOW)
            await pipe.execute()
            await audit(s, email, "login.failed", ip=ip)
            await s.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That email or password is not right.")
        await redis.delete(keys[0])
        admin.last_login_at = datetime.now(timezone.utc)
        await audit(s, admin.email, "login", admin_id=admin.id, ip=ip)
        await s.commit()
        return await _issue(admin)


@router.post("/refresh", response_model=PTokens)
async def refresh(body: PRefresh):
    try:
        claims = decode_token(body.refresh_token, "p_refresh")
        admin_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if not await get_redis().getdel(f"prefresh:{claims['jti']}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token already used or revoked")
    async with PlatformSession() as s:
        admin = (await s.execute(select(PlatformAdmin).where(PlatformAdmin.id == admin_id, PlatformAdmin.is_active.is_(True)))).scalar_one_or_none()
    if admin is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    return await _issue(admin)


@router.post("/logout", status_code=204)
async def logout(body: PRefresh):
    try:
        await get_redis().delete(f"prefresh:{decode_token(body.refresh_token, 'p_refresh')['jti']}")
    except jwt.PyJWTError:
        pass


@router.get("/me", response_model=PAdmin)
async def me(ctx: PlatformCtx = Depends(get_platform_ctx)):
    return ctx.admin
