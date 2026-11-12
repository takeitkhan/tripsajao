"""Authentication, tenant binding (RLS) and authorization dependencies."""
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ALL_SCOPES, PARTNER_SCOPES, SUPPORT_BLOCKED_SCOPES, effective_scopes
from app.core.db import SessionLocal, bind_tenant
from app.core.redis import get_redis
from app.core.security import decode_token, issued_before, verify_api_secret
from app.models import Partner, Tenant, User
from app.schemas.common import Pagination

_api_key = APIKeyHeader(name="X-API-KEY", auto_error=False, description="Tenant public API key")
_api_secret = APIKeyHeader(name="X-API-SECRET", auto_error=False, description="Tenant API secret")
_bearer = HTTPBearer(auto_error=False, description="Admin / partner JWT access token")


@dataclass(frozen=True)
class Principal:
    kind: Literal["api_client", "user", "partner"]
    tenant_id: UUID
    scopes: frozenset[str]
    user_id: UUID | None = None
    partner_id: UUID | None = None
    role: str | None = None
    support_session_id: UUID | None = None     # set while a super admin is helping this tenant
    support_admin: str | None = None
    support_expires: float | None = None


@dataclass
class TenantContext:
    session: AsyncSession      # transaction already bound to the tenant -> RLS active
    tenant: Tenant
    principal: Principal


def _unauth() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing credentials",
                         headers={"WWW-Authenticate": "Bearer"})


# --- pre-auth tenant lookups go through SECURITY DEFINER SQL functions (RLS would hide the row) ---
async def _tenant_via(session: AsyncSession, fn: str, cast: str, value: str) -> Tenant | None:
    stmt = select(Tenant).from_statement(
        text(f"SELECT * FROM {fn}(CAST(:v AS {cast}))").bindparams(v=value))
    return (await session.execute(stmt)).scalar_one_or_none()


async def tenant_by_api_key(session: AsyncSession, key: str) -> Tenant | None:
    return await _tenant_via(session, "app_tenant_by_api_key", "text", key)


async def tenant_by_domain(session: AsyncSession, domain: str) -> Tenant | None:
    return await _tenant_via(session, "app_tenant_by_domain", "text", domain)


async def tenant_by_id(session: AsyncSession, tenant_id: str) -> Tenant | None:
    return await _tenant_via(session, "app_tenant_by_id", "uuid", tenant_id)


async def _authenticate(session: AsyncSession, api_key: str | None, api_secret: str | None,
                        bearer: HTTPAuthorizationCredentials | None) -> tuple[Tenant, Principal]:
    if api_key:
        tenant = await tenant_by_api_key(session, api_key)
        if not (tenant and api_secret and verify_api_secret(api_secret, tenant.api_secret_hash)):
            raise _unauth()
        await bind_tenant(session, tenant.id)
        return tenant, Principal("api_client", tenant.id, frozenset(tenant.api_scopes or []))

    if bearer:
        try:
            claims = decode_token(bearer.credentials, "access")
            sub = UUID(claims["sub"])
            tid = UUID(claims["tid"])
        except (jwt.PyJWTError, ValueError):
            raise _unauth()
        tenant = await tenant_by_id(session, str(tid))
        if tenant is None:
            raise _unauth()
        await bind_tenant(session, tenant.id)
        if claims.get("principal") == "user":
            user = (await session.execute(
                select(User).where(User.id == sub, User.tenant_id == tenant.id, User.is_active.is_(True))
            )).scalar_one_or_none()
            if user is None:
                raise _unauth()
            redis = get_redis()
            changed = await redis.get(f"pwchanged:{user.id}")           # password reset or changed after this token was issued
            if changed and issued_before(claims, changed):
                raise _unauth()
            scopes = effective_scopes(user.role.value, user.permissions)
            if claims.get("sess"):                                      # support session: must still be open, and is limited
                if not await redis.exists(f"support:active:{claims['sess']}"):
                    raise _unauth()
                scopes = frozenset(s for s in scopes if s not in SUPPORT_BLOCKED_SCOPES) if "*" not in scopes else \
                    frozenset(s for s in ALL_SCOPES if s not in SUPPORT_BLOCKED_SCOPES)
                return tenant, Principal("user", tenant.id, scopes, user_id=user.id, role=user.role.value,
                                         support_session_id=UUID(claims["sess"]), support_admin=claims.get("imp"),
                                         support_expires=float(claims["exp"]))
            return tenant, Principal("user", tenant.id, scopes, user_id=user.id, role=user.role.value)
        if claims.get("principal") == "partner":
            partner = (await session.execute(
                select(Partner).where(Partner.id == sub, Partner.tenant_id == tenant.id, Partner.is_active.is_(True))
            )).scalar_one_or_none()
            if partner is None:
                raise _unauth()
            return tenant, Principal("partner", tenant.id, PARTNER_SCOPES, partner_id=partner.id)
    raise _unauth()


async def get_ctx(request: Request, api_key: str | None = Depends(_api_key), api_secret: str | None = Depends(_api_secret),
                  bearer: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AsyncIterator[TenantContext]:
    """One DB transaction per request, bound to the authenticated tenant.
    Commit on success, rollback on any exception."""
    session = SessionLocal()
    try:
        tenant, principal = await _authenticate(session, api_key, api_secret, bearer)
        yield TenantContext(session=session, tenant=tenant, principal=principal)
        await session.commit()
        if principal.support_session_id and request.method not in ("GET", "HEAD", "OPTIONS"):
            from app.services.platform import record_support_change      # every change made in a support session is logged
            await record_support_change(principal, tenant, request)
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


def authorize(*scopes: str):
    """Require ANY of the given scopes (JWT roles are expanded to scopes; ADMIN holds '*')."""
    async def _dep(ctx: TenantContext = Depends(get_ctx)) -> TenantContext:
        have = ctx.principal.scopes
        if "*" not in have and not have.intersection(scopes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing scope: {' or '.join(scopes)}")
        return ctx
    _dep.__scopes__ = scopes          # read by the API-docs generator
    return _dep


# ----------------------------------------------------------------------------- helpers
async def get_or_404(ctx: TenantContext, model: type, obj_id: UUID, what: str | None = None) -> Any:
    obj = await ctx.session.get(model, obj_id)
    # RLS already hides other tenants' rows; the explicit check is defence-in-depth.
    if obj is None or getattr(obj, "tenant_id", ctx.tenant.id) != ctx.tenant.id:
        raise HTTPException(404, f"{what or model.__name__} not found")
    return obj


async def persist(session: AsyncSession, obj: Any, conflict: str = "Resource already exists") -> Any:
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, conflict) from exc
    await session.refresh(obj)
    return obj


async def paginate(session: AsyncSession, stmt, pg: Pagination) -> dict:
    total = (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await session.execute(stmt.limit(pg.limit).offset(pg.offset))).scalars().all()
    return {"items": rows, "total": total, "limit": pg.limit, "offset": pg.offset}
