"""Public, unauthenticated short-link endpoint: /go/{vanity_code}[/{property_slug}].

Serve it on the tenant's own domain (reverse-proxy `/go/*` to this API) so the HTTP-only cookie is first-party
for the tenant's website. The URL the visitor ends up on is clean - no query parameters."""
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.redis import get_redis
from app.core.security import open_referral, seal_referral

router = APIRouter(tags=["affiliate"])
_CODE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _safe_path(path: str) -> str:
    return path if path.startswith("/") and not path.startswith("//") else "/"


async def _redirect(vanity_code: str, property_slug: str | None, request: Request) -> RedirectResponse:
    if not _CODE.match(vanity_code) or (property_slug and not _SLUG.match(property_slug)):
        raise HTTPException(404, "Not found")
    async with SessionLocal() as session:       # no tenant bound: only the SECURITY DEFINER function may read
        row = (await session.execute(text("SELECT * FROM app_resolve_vanity(CAST(:c AS text))"), {"c": vanity_code})).mappings().first()
    if row is None:
        raise HTTPException(404, "Not found")

    cfg = row["settings_json"] or {}
    if property_slug:
        path = _safe_path(str(cfg.get("property_path_template", "/properties/{slug}")).replace("{slug}", property_slug))
    else:
        path = _safe_path(str(cfg.get("landing_path", "/")))
    resp = RedirectResponse(f"https://{row['domain']}{path}", status_code=302)   # host comes from OUR DB -> no open redirect

    existing = open_referral(request.cookies.get(settings.referral_cookie_name), settings.referral_cookie_days * 86400)
    keep_first = cfg.get("attribution_model") == "first_click" and existing and existing.get("t") == str(row["tenant_id"])
    if not keep_first:
        resp.set_cookie(settings.referral_cookie_name, seal_referral(row["tenant_id"], row["partner_id"]),
                        max_age=settings.referral_cookie_days * 86400, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", path="/")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    try:
        await get_redis().incr(f"clicks:{row['partner_id']}")       # cheap click counter
    except Exception:  # noqa: BLE001
        pass
    return resp


@router.get("/go/{vanity_code}", status_code=302, response_class=RedirectResponse,
            summary="Short link: bind encrypted attribution cookie, redirect to clean landing page")
async def go(vanity_code: str, request: Request):
    return await _redirect(vanity_code, None, request)


@router.get("/go/{vanity_code}/{property_slug}", status_code=302, response_class=RedirectResponse,
            summary="Short link straight to a property page")
async def go_property(vanity_code: str, property_slug: str, request: Request):
    return await _redirect(vanity_code, property_slug, request)
