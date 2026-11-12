"""Public showcase for the Trip Sajao marketing site: a few real, public details (names, places, photos, from-prices)
of businesses the super admin has chosen to feature. No guest data, no payment data, no API key needed."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.core.db import PlatformSession

router = APIRouter(prefix="/public/showcase", tags=["showcase"])

_KIND = {"resort": "RESORT", "hotel": "HOTEL", "houseboat": "HOUSEBOAT"}
_FLAG = "t.status = 'ACTIVE' AND t.settings_json->>'showcase' = 'true'"


def _photo(meta: dict, media: list | None = None) -> str | None:
    for m in (meta or {}).get("media") or []:
        if isinstance(m, dict) and m.get("url") and m.get("type", "image") == "image":
            return m["url"]
    return None


@router.get("", summary="Featured properties or events for the public website",
            description="`kind` is resort, hotel, houseboat or events. Returns at most `limit` items from businesses the platform has chosen to feature.")
async def showcase(kind: Literal["resort", "hotel", "houseboat", "events"], limit: int = Query(6, ge=1, le=12)):
    async with PlatformSession() as s:
        if kind == "events":
            rows = (await s.execute(text(f"""
                SELECT e.title, e.location, e.starts_on, e.ends_on, e.price, e.currency, e.seats, e.cover_image, t.name AS business
                FROM tour_events e JOIN tenants t ON t.id = e.tenant_id
                WHERE {_FLAG} AND e.status = 'PUBLISHED' AND e.ends_on >= current_date
                ORDER BY e.starts_on LIMIT :n"""), {"n": limit})).mappings().all()
            return {"kind": kind, "items": [{"title": r["title"], "location": r["location"], "starts_on": r["starts_on"], "ends_on": r["ends_on"],
                                             "price": str(r["price"]), "currency": r["currency"], "seats": r["seats"], "image": r["cover_image"], "business": r["business"]} for r in rows]}
        rows = (await s.execute(text(f"""
            SELECT p.id, p.name, p.location, p.metadata, t.name AS business,
                   count(u.id) FILTER (WHERE u.is_active) AS units,
                   count(u.id) FILTER (WHERE u.is_active AND u.status = 'AVAILABLE') AS open_units,
                   min(r.weekday_price) AS from_price,
                   coalesce(t.settings_json->'company'->>'currency', 'BDT') AS currency
            FROM properties p JOIN tenants t ON t.id = p.tenant_id
            LEFT JOIN units u ON u.property_id = p.id AND u.tenant_id = p.tenant_id
            LEFT JOIN pricing_rules r ON r.unit_id = u.id AND r.tenant_id = u.tenant_id
            WHERE {_FLAG} AND p.is_active AND p.type = :ty
            GROUP BY p.id, t.id ORDER BY p.created_at LIMIT :n"""), {"ty": _KIND[kind], "n": limit})).mappings().all()
    return {"kind": kind, "items": [{"name": r["name"], "location": r["location"], "business": r["business"], "units": r["units"], "open_units": r["open_units"],
                                     "from_price": None if r["from_price"] is None else str(Decimal(r["from_price"]).quantize(Decimal("1"))),
                                     "currency": r["currency"], "image": _photo(r["metadata"])} for r in rows]}
