"""Super admin operations: usage numbers, audit trail, support sessions."""
import secrets
import string
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import text

from app.core.db import PlatformSession
from app.models import PlatformAudit, SupportSession


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None))


def generate_password(n: int = 16) -> str:
    """Readable, strong, always satisfies the 10+ characters rule (no look-alike characters)."""
    letters = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    digits, symbols = "23456789", "-_.!"
    pool = letters + digits + symbols
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(n))
        if any(c in digits for c in pw) and any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c in symbols for c in pw):
            return pw


async def audit(session, admin_email: str, action: str, *, admin_id: UUID | None = None, tenant=None, ip: str | None = None, **detail: Any) -> None:
    session.add(PlatformAudit(admin_id=admin_id, admin_email=admin_email, action=action, ip=ip, detail_json=detail,
                              tenant_id=getattr(tenant, "id", None), tenant_name=getattr(tenant, "name", None)))


async def record_support_change(principal, tenant, request: Request) -> None:
    """Called after a change made inside a support session was saved."""
    async with PlatformSession() as s:
        await s.execute(text("UPDATE support_sessions SET change_count = change_count + 1 WHERE id = :i"), {"i": principal.support_session_id})
        await audit(s, principal.support_admin or "unknown", "support.change", tenant=tenant, ip=client_ip(request),
                    support_session=str(principal.support_session_id), method=request.method, path=request.url.path)
        await s.commit()


async def usage_for(session, ids: list[UUID]) -> dict[UUID, dict]:
    """Counts per tenant, gathered in a handful of grouped queries instead of one query per tenant."""
    out = {i: {"properties": 0, "units": 0, "partners": 0, "users": 0, "bookings": 0, "bookings_30d": 0, "revenue": {},
               "media_files": 0, "media_bytes": 0, "last_booking_at": None} for i in ids}
    if not ids:
        return out
    arg = {"ids": [str(i) for i in ids]}
    for key, sql in (
        ("properties", "SELECT tenant_id, count(*) FROM properties WHERE is_active AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
        ("units", "SELECT tenant_id, count(*) FROM units WHERE is_active AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
        ("partners", "SELECT tenant_id, count(*) FROM partners WHERE is_active AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
        ("users", "SELECT tenant_id, count(*) FROM users WHERE is_active AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
        ("bookings", "SELECT tenant_id, count(*) FROM bookings WHERE status = 'CONFIRMED' AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
        ("bookings_30d", "SELECT tenant_id, count(*) FROM bookings WHERE status <> 'CANCELLED' AND created_at > now() - interval '30 days' "
                         "AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"),
    ):
        for tid, n in (await session.execute(text(sql), arg)).all():
            out[tid][key] = n
    for tid, cur, amt in (await session.execute(text(
            "SELECT tenant_id, currency, sum(paid_amount) FROM bookings WHERE status = 'CONFIRMED' AND tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1, 2"), arg)).all():
        out[tid]["revenue"][cur] = str(amt)
    for tid, n, b in (await session.execute(text(
            "SELECT tenant_id, count(*), coalesce(sum(size_bytes), 0) FROM media_assets WHERE tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"), arg)).all():
        out[tid]["media_files"], out[tid]["media_bytes"] = n, int(b)
    for tid, at in (await session.execute(text(
            "SELECT tenant_id, max(created_at) FROM bookings WHERE tenant_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1"), arg)).all():
        out[tid]["last_booking_at"] = at
    return out


def tenant_row(t, usage: dict) -> dict:
    return {"id": t.id, "name": t.name, "domain": t.domain, "status": t.status, "status_reason": t.status_reason,
            "created_at": t.created_at, "limits": t.limits_json or {}, "profile": t.profile_json or {}, "usage": usage, "showcase": bool((t.settings_json or {}).get("showcase"))}


async def create_tenant_with_admin(session, *, name: str, domain: str, admin_name: str, admin_email: str, admin_password: str,
                                   timezone_name: str, status: str, limits: dict, profile: dict):
    from app.core.constants import DEFAULT_API_CLIENT_SCOPES
    from app.core.security import generate_api_credentials, hash_api_secret, hash_password
    from app.models import Role, Tenant, User
    key, secret = generate_api_credentials()
    t = Tenant(name=name, domain=domain, api_key=key, api_secret_hash=hash_api_secret(secret), api_scopes=DEFAULT_API_CLIENT_SCOPES,
               status=status, is_active=(status == "ACTIVE"), limits_json=limits, profile_json=profile,
               settings_json={"timezone": timezone_name, "deposit_percent": 50, "hold_seconds": 600, "min_payout": 1000,
                              "attribution_model": "last_click", "landing_path": "/", "property_path_template": "/properties/{slug}",
                              "company": {"name": name}})
    session.add(t)
    await session.flush()
    session.add(User(tenant_id=t.id, name=admin_name, email=admin_email.lower(), password_hash=hash_password(admin_password), role=Role.ADMIN))
    await session.flush()
    return t, key, secret


def now() -> datetime:
    return datetime.now(timezone.utc)
