from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.constants import ALL_SCOPES, KEY_FORBIDDEN_SCOPES
from app.core.db import PlatformSession, SessionLocal, bind_tenant
from app.core.deps import TenantContext, authorize, get_ctx, tenant_by_domain
from app.core.redis import get_redis
from app.core.security import (DUMMY_HASH, create_token, decode_token, generate_api_credentials, hash_api_secret,
                               hash_password, issued_before, verify_password)
from app.models import ChannelAgreement, ChannelCancellation, EventBooking, PlatformAudit, Partner, SupportSession, Tenant, User
from app.schemas.auth import (ApiCredentialsOut, ApiKeyOut, ApiKeyRequest, ChangePassword, LoginRequest, MeOut, RefreshRequest, SupportExchange, SupportToken,
                              TokenPair)

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILS, FAIL_WINDOW = 5, 900


async def _issue(tenant_id: UUID, sub: UUID, principal: str) -> TokenPair:
    access, _ = create_token(sub=str(sub), tenant_id=str(tenant_id), principal=principal, typ="access",
                             expires=timedelta(minutes=settings.access_token_minutes))
    refresh, jti = create_token(sub=str(sub), tenant_id=str(tenant_id), principal=principal, typ="refresh",
                                expires=timedelta(days=settings.refresh_token_days))
    await get_redis().set(f"refresh:{jti}", f"{tenant_id}:{principal}:{sub}", ex=settings.refresh_token_days * 86400)
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=settings.access_token_minutes * 60)


INACTIVE_TEXT = {
    "PENDING": "Your registration is waiting for approval. You can sign in as soon as it is approved.",
    "SUSPENDED": "This account is suspended. Please contact support.",
    "REJECTED": "This registration was not approved. Please contact support.",
}


async def _explain_inactive(body: LoginRequest) -> None:
    """Only someone who knows the right password learns that the business exists but is not active."""
    async with PlatformSession() as s:
        t = (await s.execute(select(Tenant).where(Tenant.domain == body.tenant_domain.lower()))).scalar_one_or_none()
        if t is None or t.status == "ACTIVE":
            return
        model = User if body.principal == "user" else Partner
        acct = (await s.execute(select(model).where(model.tenant_id == t.id, model.email == body.email.lower()))).scalar_one_or_none()
        if acct and verify_password(acct.password_hash, body.password):
            raise HTTPException(status.HTTP_403_FORBIDDEN, INACTIVE_TEXT.get(t.status, "This account is not active."))


async def _login_by_email(body: LoginRequest) -> TokenPair:
    """No business domain given: find the account by e-mail. Works when the e-mail + password match exactly one business."""
    redis = get_redis()
    email = body.email.lower()
    fail_key = f"loginfail:any:{body.principal}:{email}"
    if int(await redis.get(fail_key) or 0) >= MAX_FAILS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
    model = User if body.principal == "user" else Partner
    async with PlatformSession() as s:
        rows = (await s.execute(select(model, Tenant).join(Tenant, Tenant.id == model.tenant_id)
                                .where(model.email == email, model.is_active.is_(True)).limit(5))).all()
        if not rows:
            verify_password(DUMMY_HASH, body.password)
        hits = [(a, t) for a, t in rows if verify_password(a.password_hash, body.password)]
    active = [(a, t) for a, t in hits if t.status == "ACTIVE"]
    if len(active) == 1:
        await redis.delete(fail_key)
        return await _issue(active[0][1].id, active[0][0].id, body.principal)
    if len(active) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "This e-mail is used in more than one business. Enter your business domain.")
    if hits:                                             # right password, but the business is not active: say why
        raise HTTPException(status.HTTP_403_FORBIDDEN, INACTIVE_TEXT.get(hits[0][1].status, "This account is not active."))
    pipe = redis.pipeline()
    pipe.incr(fail_key)
    pipe.expire(fail_key, FAIL_WINDOW)
    await pipe.execute()
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")


@router.post("/login", response_model=TokenPair, summary="Tenant admin / partner login (business domain is optional)")
async def login(body: LoginRequest):
    if not (body.tenant_domain or "").strip():
        return await _login_by_email(body)
    redis = get_redis()
    async with SessionLocal() as session:
        tenant = await tenant_by_domain(session, body.tenant_domain.lower())
        if tenant is None:
            verify_password(DUMMY_HASH, body.password)
            await _explain_inactive(body)          # right password on a pending or suspended business: say why
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        await bind_tenant(session, tenant.id)

        fail_key = f"loginfail:{tenant.id}:{body.principal}:{body.email.lower()}"
        if int(await redis.get(fail_key) or 0) >= MAX_FAILS:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")

        model = User if body.principal == "user" else Partner
        account = (await session.execute(select(model).where(
            model.tenant_id == tenant.id, model.email == body.email.lower(), model.is_active.is_(True)))).scalar_one_or_none()
        ok = verify_password(account.password_hash if account else DUMMY_HASH, body.password) and account is not None
        if not ok:
            pipe = redis.pipeline()
            pipe.incr(fail_key)
            pipe.expire(fail_key, FAIL_WINDOW)
            await pipe.execute()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        await redis.delete(fail_key)
        return await _issue(tenant.id, account.id, body.principal)


@router.post("/refresh", response_model=TokenPair, summary="Rotate refresh token")
async def refresh(body: RefreshRequest):
    try:
        claims = decode_token(body.refresh_token, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    # single-use: GETDEL makes replay of a stolen/used token fail
    if not await get_redis().getdel(f"refresh:{claims['jti']}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token already used or revoked")
    tenant_id, sub = UUID(claims["tid"]), UUID(claims["sub"])
    async with SessionLocal() as session:
        await bind_tenant(session, tenant_id)
        model = User if claims["principal"] == "user" else Partner
        active = (await session.execute(select(model.id).where(model.id == sub, model.is_active.is_(True)))).scalar_one_or_none()
    if not active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    changed = await get_redis().get(f"pwchanged:{sub}")
    if changed and issued_before(claims, changed):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your password changed. Sign in again.")
    return await _issue(tenant_id, sub, claims["principal"])


@router.post("/logout", status_code=204, summary="Revoke a refresh token")
async def logout(body: RefreshRequest):
    try:
        await get_redis().delete(f"refresh:{decode_token(body.refresh_token, 'refresh')['jti']}")
    except jwt.PyJWTError:
        pass


@router.get("/me", response_model=MeOut, summary="Who am I (principal + scopes)")
async def me(ctx: TenantContext = Depends(get_ctx)):
    p = ctx.principal
    support = ({"admin": p.support_admin, "expires_at": datetime.fromtimestamp(p.support_expires, timezone.utc).isoformat()}
               if p.support_session_id else None)
    channel = None
    if p.kind != "partner":
        rows = (await ctx.session.execute(select(ChannelAgreement.supplier_tenant_id, ChannelAgreement.status))).all()
        mine = ctx.tenant.id
        open_cancels = (await ctx.session.execute(select(func.count()).select_from(ChannelCancellation).where(
            ChannelCancellation.tenant_id == mine, ChannelCancellation.status == "REQUESTED"))).scalar_one()
        channel = {"has_agreements": any(st in ("ACTIVE", "PAUSED", "ENDED") for _, st in rows),
                   "sells_for_others": any(sid != mine and st in ("ACTIVE", "PAUSED") for sid, st in rows),
                   "waiting": sum(1 for sid, st in rows if (st == "REQUESTED" and sid == mine) or (st == "INVITED" and sid != mine)) + open_cancels,
                   "event_waiting": (await ctx.session.execute(select(func.count()).select_from(EventBooking).where(
                       EventBooking.tenant_id == mine, EventBooking.status == "PAYMENT_SUBMITTED"))).scalar_one()}
    company = (ctx.tenant.settings_json or {}).get("company", {}) or {}
    person = None
    if p.kind in ("user", "partner"):
        acct = await ctx.session.get(User if p.kind == "user" else Partner, p.user_id or p.partner_id)
        person = getattr(acct, "name", None)
    return MeOut(kind=p.kind, tenant_id=p.tenant_id, user_id=p.user_id, partner_id=p.partner_id, role=p.role,
                 scopes=sorted(p.scopes), support=support, tenant_name=company.get("name") or ctx.tenant.name, tenant_domain=ctx.tenant.domain, tenant_logo=company.get("logo_url"),
                 person_name=person, channel=channel)


def _check_scopes(scopes: list[str]) -> list[str]:
    bad = [x for x in scopes if x not in ALL_SCOPES or x in KEY_FORBIDDEN_SCOPES]
    if bad:
        raise HTTPException(422, f"Scopes not allowed for API keys: {bad}")
    return sorted(set(scopes))


@router.get("/api-credentials", response_model=ApiCredentialsOut, summary="The current API key and its permissions (the secret is never stored in readable form)")
async def api_credentials(ctx: TenantContext = Depends(authorize("api_keys:manage"))):
    t = ctx.tenant
    return ApiCredentialsOut(api_key=t.api_key, scopes=list(t.api_scopes or []), has_secret=bool(t.api_secret_hash))


@router.put("/api-keys/scopes", response_model=ApiCredentialsOut, summary="Change what the current key may do (key and secret stay the same)")
async def set_api_scopes(body: ApiKeyRequest, ctx: TenantContext = Depends(authorize("api_keys:manage"))):
    ctx.tenant.api_scopes = _check_scopes(body.scopes)
    await ctx.session.flush()
    return ApiCredentialsOut(api_key=ctx.tenant.api_key, scopes=ctx.tenant.api_scopes, has_secret=bool(ctx.tenant.api_secret_hash))


@router.post("/api-keys/rotate-secret", response_model=ApiKeyOut, summary="Change only the secret; the key and permissions stay the same")
async def rotate_api_secret(ctx: TenantContext = Depends(authorize("api_keys:manage"))):
    """The old secret stops working at once. The new secret is returned once and cannot be shown again."""
    _, secret = generate_api_credentials()
    ctx.tenant.api_secret_hash = hash_api_secret(secret)
    await ctx.session.flush()
    return ApiKeyOut(api_key=ctx.tenant.api_key, api_secret=secret, scopes=list(ctx.tenant.api_scopes or []))


@router.post("/api-keys", response_model=ApiKeyOut, status_code=201, summary="Generate / rotate API key + secret")
async def generate_api_key(body: ApiKeyRequest, ctx: TenantContext = Depends(authorize("api_keys:manage"))):
    """Rotates the tenant's credentials (old pair stops working immediately). The secret is returned once."""
    scopes = _check_scopes(body.scopes)
    key, secret = generate_api_credentials()
    ctx.tenant.api_key, ctx.tenant.api_secret_hash, ctx.tenant.api_scopes = key, hash_api_secret(secret), scopes
    await ctx.session.flush()
    return ApiKeyOut(api_key=key, api_secret=secret, scopes=ctx.tenant.api_scopes)


@router.post("/change-password", status_code=204, summary="Change my own password")
async def change_password(body: ChangePassword, ctx: TenantContext = Depends(get_ctx)):
    p = ctx.principal
    if p.kind not in ("user", "partner") or p.support_session_id:
        raise HTTPException(403, "Passwords can only be changed by the account owner.")
    model = User if p.kind == "user" else Partner
    account = await ctx.session.get(model, p.user_id or p.partner_id)
    if account is None or not verify_password(account.password_hash, body.current_password):
        raise HTTPException(422, "The current password is not right.")
    account.password_hash = hash_password(body.new_password)
    await ctx.session.flush()
    await get_redis().set(f"pwchanged:{account.id}", str(datetime.now(timezone.utc).timestamp()), ex=30 * 86400)


@router.post("/support-exchange", response_model=SupportToken, summary="Open a support session (used by the super admin portal)")
async def support_exchange(body: SupportExchange):
    """Swaps the one-time code from the super admin portal for a short-lived access token."""
    redis = get_redis()
    sid = await redis.getdel(f"support:{body.code}")
    if not sid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This support link has expired. Open it again from the super admin portal.")
    async with PlatformSession() as s:
        sess = await s.get(SupportSession, UUID(sid))
        left = (sess.expires_at - datetime.now(timezone.utc)).total_seconds() if sess else 0
        if sess is None or sess.ended_at or left <= 0:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This support session has ended.")
        token, _ = create_token(sub=str(sess.user_id), tenant_id=str(sess.tenant_id), principal="user", typ="access", expires=timedelta(seconds=left),
                                extra={"sess": str(sess.id), "imp": sess.admin_email})
    return SupportToken(access_token=token, expires_in=int(left))


@router.post("/support-end", status_code=204, summary="End the current support session")
async def support_end(ctx: TenantContext = Depends(get_ctx)):
    sid = ctx.principal.support_session_id
    if not sid:
        raise HTTPException(409, "This is not a support session.")
    await get_redis().delete(f"support:active:{sid}")
    async with PlatformSession() as s:
        sess = await s.get(SupportSession, sid)
        if sess and not sess.ended_at:
            sess.ended_at, sess.ended_by = datetime.now(timezone.utc), "admin"
            s.add(PlatformAudit(admin_email=sess.admin_email, action="support.end", tenant_id=sess.tenant_id, tenant_name=sess.tenant_name,
                                detail_json={"session": str(sid), "changes": sess.change_count}))
        await s.commit()
