"""Authentication for the super admin portal. Platform tokens use their own token types, so a tenant token can
never open a platform route and a platform token can never open a tenant route."""
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.db import PlatformSession
from app.core.security import decode_token
from app.models import PlatformAdmin
from app.services.platform import client_ip

_bearer = HTTPBearer(auto_error=False)


@dataclass
class PlatformCtx:
    session: object
    admin: PlatformAdmin
    ip: str | None


async def get_platform_ctx(request: Request, bearer: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AsyncIterator[PlatformCtx]:
    unauth = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing credentials", headers={"WWW-Authenticate": "Bearer"})
    if not bearer:
        raise unauth
    try:
        claims = decode_token(bearer.credentials, "p_access")
        admin_id = UUID(claims["sub"])
        if claims.get("principal") != "platform":
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise unauth
    session = PlatformSession()
    try:
        admin = (await session.execute(select(PlatformAdmin).where(PlatformAdmin.id == admin_id, PlatformAdmin.is_active.is_(True)))).scalar_one_or_none()
        if admin is None:
            raise unauth
        yield PlatformCtx(session=session, admin=admin, ip=client_ip(request))
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()
