"""Public contact form of the marketing site. Anyone may send; the super admin reads the messages."""
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.db import PlatformSession
from app.core.redis import get_redis
from app.models import ContactMessage
from app.services.platform import client_ip

router = APIRouter(prefix="/public/contact", tags=["public"], include_in_schema=False)
_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TYPES = {"resort", "hotel", "houseboat", "events", "agency", "other"}


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    phone: str | None = Field(None, max_length=40)
    business_type: str = "other"
    message: str = Field(min_length=3, max_length=2000)
    lang: str = "en"
    website: str | None = Field(None, max_length=200, description="Honeypot: real people leave it empty.")

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _MAIL.match(v):
            raise ValueError("Enter a valid email")
        return v


@router.post("", status_code=201)
async def send(body: ContactIn, request: Request):
    if body.website:                       # a bot filled the hidden field: pretend it worked, store nothing
        return {"ok": True}
    ip = client_ip(request) or "?"
    r = get_redis()
    for key, maximum, secs in ((f"contact:ip:{ip}", 5, 3600), (f"contact:mail:{body.email}", 3, 86400)):
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, secs)
        if n > maximum:
            raise HTTPException(429, "Too many messages. Please try again later.")
    async with PlatformSession() as s:
        s.add(ContactMessage(name=body.name.strip(), email=body.email, phone=(body.phone or "").strip() or None,
                             business_type=body.business_type if body.business_type in TYPES else "other",
                             message=body.message.strip(), lang="bn" if body.lang == "bn" else "en", ip=ip[:64]))
        await s.commit()
    return {"ok": True}
