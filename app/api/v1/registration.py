"""Public business registration (used by the /register page)."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.db import PlatformSession
from app.core.redis import get_redis
from app.models import Tenant
from app.schemas.platform import Register, clean_domain
from app.services.platform import audit, client_ip, create_tenant_with_admin

router = APIRouter(prefix="/public", tags=["public"], include_in_schema=False)


async def _limit(key: str, maximum: int, seconds: int) -> None:
    r = get_redis()
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, seconds)
    if n > maximum:
        raise HTTPException(429, "Too many attempts. Please try again later.")


@router.get("/register/config")
async def config():
    return {"mode": settings.registration_mode,
            "business_types": [["RESORT", "Resort"], ["HOTEL", "Hotel"], ["HOUSEBOAT", "Houseboat"], ["TRAVEL_AGENCY", "Travel agency"], ["OTHER", "Other"]]}


@router.get("/register/check")
async def check(request: Request, domain: str = Query(min_length=1, max_length=253)):
    await _limit(f"regcheck:{client_ip(request)}", 60, 600)
    try:
        d = clean_domain(domain)
    except ValueError as e:
        return {"available": False, "message": str(e)}
    async with PlatformSession() as s:
        taken = (await s.execute(select(Tenant.id).where(Tenant.domain == d))).first()
    return {"available": not taken, "domain": d, "message": "That name is already taken." if taken else None}


@router.post("/register", status_code=201)
async def register(body: Register, request: Request):
    mode = settings.registration_mode
    if mode == "closed":
        raise HTTPException(403, "Registration is closed right now.")
    ip = client_ip(request)
    await _limit(f"register:{ip}", 5, 3600)
    if body.website:                                            # a bot filled the hidden field: pretend it worked
        return {"status": "PENDING", "message": "Thanks! We will review your registration.", "domain": body.domain}
    state = "ACTIVE" if mode == "open" else "PENDING"
    async with PlatformSession() as s:
        if (await s.execute(select(Tenant.id).where(Tenant.domain == body.domain))).first():
            raise HTTPException(409, "That business domain is already taken. Please choose another.")
        t, _key, _secret = await create_tenant_with_admin(
            s, name=body.business_name.strip(), domain=body.domain, admin_name=body.owner_name.strip(), admin_email=str(body.email),
            admin_password=body.password, timezone_name="UTC", status=state, limits={},
            profile={"owner": body.owner_name.strip(), "email": str(body.email).lower(), "phone": body.phone, "country": body.country,
                     "business_type": body.business_type, "joined_via": "self-registration", "ip": ip,
                     "terms_accepted_at": datetime.now(timezone.utc).isoformat()})
        await audit(s, "self-registration", "tenant.register", tenant=t, ip=ip, status=state, business_type=body.business_type)
        await s.commit()
    return {"status": state, "domain": body.domain,
            "message": ("Your account is ready. You can sign in now." if state == "ACTIVE"
                        else "Thanks! We received your registration. You can sign in as soon as it is approved.")}
