"""Super admin portal API. Everything here is cross-tenant and uses the platform (BYPASSRLS) database role.
Hidden from the public OpenAPI so it does not appear in tenants' API documentation."""
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.platform_deps import PlatformCtx, get_platform_ctx
from app.core.redis import get_redis
from app.core.security import hash_password
from app.models import ContactMessage, PlatformAudit, Role, SupportSession, Tenant, User
from app.schemas.platform import Reason, ResetPassword, SupportStart, TenantCreate, TenantUpdate
from app.services.platform import audit, create_tenant_with_admin, generate_password, now, tenant_row, usage_for

router = APIRouter(prefix="/platform", tags=["platform"], include_in_schema=False)
STATUSES = ("ACTIVE", "PENDING", "SUSPENDED", "REJECTED")


async def _tenant(ctx: PlatformCtx, tenant_id: UUID) -> Tenant:
    t = await ctx.session.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(404, "Business not found")
    return t


def _page(rows, total, limit, offset):
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------------------------------------ overview
@router.get("/overview")
async def overview(ctx: PlatformCtx = Depends(get_platform_ctx)):
    s = ctx.session
    one = lambda sql, **p: s.execute(text(sql), p)  # noqa: E731
    by_status = dict((await one("SELECT status, count(*) FROM tenants GROUP BY 1")).all())
    totals = (await one("""SELECT (SELECT count(*) FROM properties WHERE is_active), (SELECT count(*) FROM units WHERE is_active),
                                  (SELECT count(*) FROM bookings WHERE status = 'CONFIRMED'),
                                  (SELECT count(*) FROM bookings WHERE status <> 'CANCELLED' AND created_at > now() - interval '30 days'),
                                  (SELECT coalesce(sum(size_bytes), 0) FROM media_assets), (SELECT count(*) FROM media_assets),
                                  (SELECT count(*) FROM users WHERE is_active), (SELECT count(*) FROM partners WHERE is_active)""")).one()
    revenue = {c: str(a) for c, a in (await one("SELECT currency, coalesce(sum(paid_amount), 0) FROM bookings WHERE status = 'CONFIRMED' GROUP BY 1 ORDER BY 2 DESC")).all()}
    months = "generate_series(date_trunc('month', now()) - interval '11 months', date_trunc('month', now()), interval '1 month')"
    new_tenants = [{"month": m, "value": n} for m, n in (await one(f"""SELECT to_char(g, 'YYYY-MM'), count(t.id) FROM {months} g
        LEFT JOIN tenants t ON date_trunc('month', t.created_at) = g AND t.status <> 'REJECTED' GROUP BY g ORDER BY g""")).all()]
    bookings_m = [{"month": m, "value": n} for m, n in (await one(f"""SELECT to_char(g, 'YYYY-MM'), count(b.id) FROM {months} g
        LEFT JOIN bookings b ON date_trunc('month', b.created_at) = g AND b.status = 'CONFIRMED' GROUP BY g ORDER BY g""")).all()]
    top = (await one("""SELECT t.id, t.name, t.domain, count(b.id) FILTER (WHERE b.status <> 'CANCELLED' AND b.created_at > now() - interval '30 days') AS n30,
                               coalesce(sum(m.size_bytes), 0) AS media
                        FROM tenants t LEFT JOIN bookings b ON b.tenant_id = t.id LEFT JOIN LATERAL
                             (SELECT sum(size_bytes) AS size_bytes FROM media_assets WHERE tenant_id = t.id) m ON true
                        WHERE t.status = 'ACTIVE' GROUP BY t.id, t.name, t.domain ORDER BY n30 DESC, t.name LIMIT 8""")).all()
    top_storage = (await one("""SELECT t.id, t.name, sum(m.size_bytes) FROM media_assets m JOIN tenants t ON t.id = m.tenant_id
                                GROUP BY t.id, t.name ORDER BY 3 DESC LIMIT 6""")).all()
    recent = (await s.execute(select(PlatformAudit).order_by(PlatformAudit.created_at.desc()).limit(8))).scalars().all()
    open_support = (await one("SELECT count(*) FROM support_sessions WHERE ended_at IS NULL AND expires_at > now()")).scalar_one()
    return {
        "tenants": {st: by_status.get(st, 0) for st in STATUSES}, "tenants_total": sum(by_status.values()),
        "properties": totals[0], "units": totals[1], "bookings": totals[2], "bookings_30d": totals[3],
        "media_bytes": int(totals[4]), "media_files": totals[5], "users": totals[6], "partners": totals[7],
        "revenue": revenue, "new_tenants_by_month": new_tenants, "bookings_by_month": bookings_m,
        "top_tenants": [{"id": i, "name": n, "domain": d, "bookings_30d": b, "media_bytes": int(m)} for i, n, d, b, m in top],
        "top_storage": [{"id": i, "name": n, "media_bytes": int(b)} for i, n, b in top_storage],
        "open_support_sessions": open_support,
        "recent_activity": [{"id": a.id, "action": a.action, "admin": a.admin_email, "tenant": a.tenant_name, "at": a.created_at} for a in recent],
    }


# ------------------------------------------------------------------------------------------ tenants
@router.get("/tenants")
async def list_tenants(status: str | None = Query(None), q: str | None = Query(None, max_length=100),
                       limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), ctx: PlatformCtx = Depends(get_platform_ctx)):
    stmt = select(Tenant)
    if status:
        if status not in STATUSES:
            raise HTTPException(422, "Unknown status")
        stmt = stmt.where(Tenant.status == status)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        stmt = stmt.where(Tenant.name.ilike(like, escape="\\") | Tenant.domain.ilike(like, escape="\\"))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(Tenant.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    usage = await usage_for(ctx.session, [t.id for t in rows])
    counts = dict((await ctx.session.execute(text("SELECT status, count(*) FROM tenants GROUP BY 1"))).all())
    return {**_page([tenant_row(t, usage[t.id]) for t in rows], total, limit, offset), "counts": {st: counts.get(st, 0) for st in STATUSES}}


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreate, ctx: PlatformCtx = Depends(get_platform_ctx)):
    if (await ctx.session.execute(select(Tenant.id).where(Tenant.domain == body.domain))).first():
        raise HTTPException(409, "That business domain is already in use.")
    password = body.admin_password or generate_password()
    t, key, secret = await create_tenant_with_admin(
        ctx.session, name=body.name.strip(), domain=body.domain, admin_name=body.admin_name.strip(), admin_email=str(body.admin_email),
        admin_password=password, timezone_name=body.timezone, status="ACTIVE", limits=body.limits.model_dump(exclude_none=True),
        profile={"owner": body.admin_name.strip(), "email": str(body.admin_email).lower(), "joined_via": "super admin"})
    await audit(ctx.session, ctx.admin.email, "tenant.create", admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, domain=t.domain)
    return {"tenant": tenant_row(t, (await usage_for(ctx.session, [t.id]))[t.id]), "admin_email": str(body.admin_email).lower(),
            "temporary_password": None if body.admin_password else password, "api_key": key, "api_secret": secret}


@router.get("/tenants/{tenant_id}")
async def tenant_detail(tenant_id: UUID, ctx: PlatformCtx = Depends(get_platform_ctx)):
    t = await _tenant(ctx, tenant_id)
    s = ctx.session
    usage = (await usage_for(s, [t.id]))[t.id]
    users = (await s.execute(select(User).where(User.tenant_id == t.id).order_by(User.created_at))).scalars().all()
    days = (await s.execute(text("""SELECT to_char(g, 'YYYY-MM-DD'), count(b.id) FILTER (WHERE b.status <> 'CANCELLED'), coalesce(sum(b.total_amount) FILTER (WHERE b.status <> 'CANCELLED'), 0)
            FROM generate_series(current_date - 29, current_date, interval '1 day') g
            LEFT JOIN bookings b ON b.tenant_id = :t AND b.created_at::date = g::date GROUP BY g ORDER BY g"""), {"t": t.id})).all()
    media_by_kind = [{"kind": k, "files": n, "bytes": int(b)} for k, n, b in (await s.execute(text(
        "SELECT kind, count(*), coalesce(sum(size_bytes), 0) FROM media_assets WHERE tenant_id = :t GROUP BY 1"), {"t": t.id})).all()]
    sessions = (await s.execute(select(SupportSession).where(SupportSession.tenant_id == t.id).order_by(SupportSession.started_at.desc()).limit(8))).scalars().all()
    trail = (await s.execute(select(PlatformAudit).where(PlatformAudit.tenant_id == t.id).order_by(PlatformAudit.created_at.desc()).limit(12))).scalars().all()
    return {**tenant_row(t, usage),
            "users": [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "is_active": u.is_active, "created_at": u.created_at} for u in users],
            "bookings_by_day": [{"day": d, "bookings": n, "value": str(v)} for d, n, v in days], "media_by_kind": media_by_kind,
            "support_sessions": [_session(x) for x in sessions],
            "activity": [{"id": a.id, "action": a.action, "admin": a.admin_email, "at": a.created_at, "detail": a.detail_json} for a in trail]}


@router.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: UUID, body: TenantUpdate, ctx: PlatformCtx = Depends(get_platform_ctx)):
    t = await _tenant(ctx, tenant_id)
    changes = {}
    if body.name and body.name.strip() != t.name:
        changes["name"] = [t.name, body.name.strip()]
        t.name = body.name.strip()
    if body.limits is not None:
        new = body.limits.model_dump(exclude_none=True)
        if new != (t.limits_json or {}):
            changes["limits"] = [t.limits_json or {}, new]
            t.limits_json = new
    if changes:
        await audit(ctx.session, ctx.admin.email, "tenant.update", admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, changes=changes)
    return tenant_row(t, (await usage_for(ctx.session, [t.id]))[t.id])


@router.post("/tenants/{tenant_id}/showcase", summary="Feature (or stop featuring) this business on the public website")
async def set_showcase(tenant_id: UUID, enabled: bool = Query(...), ctx: PlatformCtx = Depends(get_platform_ctx)):
    t = await _tenant(ctx, tenant_id)
    t.settings_json = {**(t.settings_json or {}), "showcase": bool(enabled)}
    await audit(ctx.session, ctx.admin.email, "tenant.showcase", admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, enabled=bool(enabled))
    return {"showcase": bool(enabled)}


async def _set_status(ctx: PlatformCtx, tenant_id: UUID, allowed_from: tuple[str, ...], to: str, action: str, reason: str | None):
    t = await _tenant(ctx, tenant_id)
    if t.status not in allowed_from:
        raise HTTPException(409, f"This business is {t.status.lower()}, so that action does not apply.")
    before = t.status
    t.status, t.is_active, t.status_reason = to, to == "ACTIVE", reason
    if to != "ACTIVE":
        await _close_support_sessions(ctx, t, "admin")
    await audit(ctx.session, ctx.admin.email, action, admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, reason=reason, was=before)
    return tenant_row(t, (await usage_for(ctx.session, [t.id]))[t.id])


@router.post("/tenants/{tenant_id}/approve")
async def approve(tenant_id: UUID, ctx: PlatformCtx = Depends(get_platform_ctx)):
    return await _set_status(ctx, tenant_id, ("PENDING",), "ACTIVE", "tenant.approve", None)


@router.post("/tenants/{tenant_id}/reject")
async def reject(tenant_id: UUID, body: Reason, ctx: PlatformCtx = Depends(get_platform_ctx)):
    return await _set_status(ctx, tenant_id, ("PENDING",), "REJECTED", "tenant.reject", body.reason)


@router.post("/tenants/{tenant_id}/suspend")
async def suspend(tenant_id: UUID, body: Reason, ctx: PlatformCtx = Depends(get_platform_ctx)):
    return await _set_status(ctx, tenant_id, ("ACTIVE",), "SUSPENDED", "tenant.suspend", body.reason)


@router.post("/tenants/{tenant_id}/reactivate")
async def reactivate(tenant_id: UUID, ctx: PlatformCtx = Depends(get_platform_ctx)):
    return await _set_status(ctx, tenant_id, ("SUSPENDED", "REJECTED"), "ACTIVE", "tenant.reactivate", None)


# ------------------------------------------------------------------------------------------ passwords
@router.post("/tenants/{tenant_id}/users/{user_id}/reset-password")
async def reset_password(tenant_id: UUID, user_id: UUID, body: ResetPassword, ctx: PlatformCtx = Depends(get_platform_ctx)):
    t = await _tenant(ctx, tenant_id)
    u = (await ctx.session.execute(select(User).where(User.id == user_id, User.tenant_id == t.id))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "User not found")
    password = body.password or generate_password()
    u.password_hash = hash_password(password)
    u.is_active = True
    # sign this person out everywhere: tokens issued before this moment stop working
    await get_redis().set(f"pwchanged:{u.id}", str(now().timestamp()), ex=30 * 86400)
    await audit(ctx.session, ctx.admin.email, "user.reset_password", admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, user=u.email)
    return {"email": u.email, "temporary_password": None if body.password else password}


# ------------------------------------------------------------------------------------------ support sign-in
def _session(x: SupportSession) -> dict:
    state = "ended" if x.ended_at else ("expired" if x.expires_at <= now() else "open")
    return {"id": x.id, "admin": x.admin_email, "tenant_id": x.tenant_id, "tenant": x.tenant_name, "user": x.user_email, "reason": x.reason, "ip": x.ip,
            "started_at": x.started_at, "expires_at": x.expires_at, "ended_at": x.ended_at, "ended_by": x.ended_by, "changes": x.change_count, "state": state}


async def _close_support_sessions(ctx: PlatformCtx, tenant: Tenant, by: str) -> None:
    open_ = (await ctx.session.execute(select(SupportSession).where(SupportSession.tenant_id == tenant.id, SupportSession.ended_at.is_(None)))).scalars().all()
    for x in open_:
        await get_redis().delete(f"support:active:{x.id}")
        x.ended_at, x.ended_by = now(), by


@router.post("/tenants/{tenant_id}/support-session", status_code=201)
async def start_support(tenant_id: UUID, body: SupportStart, ctx: PlatformCtx = Depends(get_platform_ctx)):
    t = await _tenant(ctx, tenant_id)
    if t.status != "ACTIVE":
        raise HTTPException(409, "Only active businesses can be opened for support.")
    admin_user = (await ctx.session.execute(select(User).where(User.tenant_id == t.id, User.role == Role.ADMIN, User.is_active.is_(True))
                                            .order_by(User.created_at).limit(1))).scalar_one_or_none()
    if admin_user is None:
        raise HTTPException(409, "This business has no active admin user.")
    minutes = settings.support_session_minutes
    sess = SupportSession(admin_id=ctx.admin.id, admin_email=ctx.admin.email, tenant_id=t.id, tenant_name=t.name, user_id=admin_user.id,
                          user_email=admin_user.email, reason=body.reason.strip(), ip=ctx.ip, expires_at=now() + timedelta(minutes=minutes))
    ctx.session.add(sess)
    await ctx.session.flush()
    import secrets
    code = secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.set(f"support:{code}", str(sess.id), ex=60)                    # one-time handover code, valid for a minute
    await redis.set(f"support:active:{sess.id}", "1", ex=minutes * 60)
    await audit(ctx.session, ctx.admin.email, "support.start", admin_id=ctx.admin.id, tenant=t, ip=ctx.ip, reason=sess.reason,
                support_session=str(sess.id), as_user=admin_user.email, minutes=minutes)
    return {"code": code, "url": f"/admin/?support={code}", "expires_in": 60, "session_minutes": minutes, "session_id": sess.id}


@router.get("/support-sessions")
async def support_sessions(tenant_id: UUID | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                           ctx: PlatformCtx = Depends(get_platform_ctx)):
    stmt = select(SupportSession)
    if tenant_id:
        stmt = stmt.where(SupportSession.tenant_id == tenant_id)
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(SupportSession.started_at.desc()).limit(limit).offset(offset))).scalars().all()
    return _page([_session(x) for x in rows], total, limit, offset)


@router.get("/audit")
async def audit_log(tenant_id: UUID | None = None, action: str | None = Query(None, max_length=60), limit: int = Query(30, ge=1, le=200),
                    offset: int = Query(0, ge=0), ctx: PlatformCtx = Depends(get_platform_ctx)):
    stmt = select(PlatformAudit)
    if tenant_id:
        stmt = stmt.where(PlatformAudit.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(PlatformAudit.action.like(action.replace("%", "") + "%"))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(PlatformAudit.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return _page([{"id": a.id, "action": a.action, "admin": a.admin_email, "tenant_id": a.tenant_id, "tenant": a.tenant_name, "ip": a.ip,
                   "at": a.created_at, "detail": a.detail_json} for a in rows], total, limit, offset)


@router.get("/channel/overdue")
async def overdue_commissions(limit: int = Query(100, ge=1, le=300), ctx: PlatformCtx = Depends(get_platform_ctx)):
    """Reseller commission that should have been paid by now, and statements the reseller says never arrived."""
    from datetime import date
    from app.models import ChannelSettlement
    today = date.today()
    rows = (await ctx.session.execute(select(ChannelSettlement).where(
        ((ChannelSettlement.status == "DUE") & (ChannelSettlement.due_date < today)) | (ChannelSettlement.status == "DISPUTED"))
        .order_by(ChannelSettlement.due_date).limit(limit))).scalars().all()
    totals = {}
    for s in rows:
        totals[s.currency] = totals.get(s.currency, 0) + s.amount
    return {"items": [{"id": s.id, "code": str(s.id)[:8].upper(), "owner": s.supplier_name, "owner_id": s.supplier_tenant_id, "reseller": s.reseller_name,
                       "reseller_id": s.reseller_tenant_id, "amount": s.amount, "currency": s.currency, "due_date": s.due_date, "status": s.status,
                       "days_overdue": max((today - s.due_date).days, 0), "dispute_reason": s.dispute_reason, "paid_reference": s.paid_reference}
                      for s in rows], "totals": [{"currency": c, "amount": v} for c, v in totals.items()]}


@router.get("/messages", summary="Messages from the website contact form")
async def messages(status: str | None = Query(None, pattern="^(NEW|DONE)$"), limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                   ctx: PlatformCtx = Depends(get_platform_ctx)):
    stmt = select(ContactMessage)
    if status:
        stmt = stmt.where(ContactMessage.status == status)
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    new = (await ctx.session.execute(select(func.count()).select_from(ContactMessage).where(ContactMessage.status == "NEW"))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(ContactMessage.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return {**_page([{"id": m.id, "name": m.name, "email": m.email, "phone": m.phone, "business_type": m.business_type, "message": m.message,
                      "lang": m.lang, "status": m.status, "created_at": m.created_at} for m in rows], total, limit, offset), "new": new}


@router.post("/messages/{message_id}/done", summary="Mark a website message as handled")
async def message_done(message_id: UUID, done: bool = Query(True), ctx: PlatformCtx = Depends(get_platform_ctx)):
    m = await ctx.session.get(ContactMessage, message_id)
    if m is None:
        raise HTTPException(404, "Message not found")
    m.status = "DONE" if done else "NEW"
    return {"status": m.status}
