import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# ---------- passwords (users & partners) ----------
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing")  # equalise timing on unknown accounts


# ---------- API key / secret ----------
def generate_api_credentials() -> tuple[str, str]:
    return "pk_" + secrets.token_urlsafe(18), "sk_" + secrets.token_urlsafe(32)


def hash_api_secret(secret: str) -> str:
    # The secret is 256-bit random, so a peppered HMAC is sufficient and keeps per-request auth fast.
    return hmac.new(settings.api_secret_pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()


def verify_api_secret(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_secret(secret), stored_hash)


# ---------- JWT ----------
def create_token(*, sub: str, tenant_id: str, principal: str, typ: str, expires: timedelta,
                 extra: dict | None = None) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    payload = {**(extra or {}), "sub": sub, "tid": tenant_id, "principal": principal, "typ": typ,
               "jti": jti, "iat": now, "iatf": now.timestamp(), "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), jti


def decode_token(token: str, expected_typ: str) -> dict:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                        options={"require": ["exp", "sub", "tid", "typ", "jti"]})
    if claims["typ"] != expected_typ:
        raise jwt.InvalidTokenError("wrong token type")
    return claims


# ---------- encrypted referral cookie (Fernet = AES-128-CBC + HMAC, authenticated) ----------
_fernet = Fernet(settings.cookie_encryption_key.encode())


def seal_referral(tenant_id: uuid.UUID | str, partner_id: uuid.UUID | str) -> str:
    return _fernet.encrypt(json.dumps({"t": str(tenant_id), "p": str(partner_id)}).encode()).decode()


def open_referral(token: str | None, max_age_seconds: int) -> dict | None:
    if not token:
        return None
    try:
        return json.loads(_fernet.decrypt(token.encode(), ttl=max_age_seconds))
    except (InvalidToken, ValueError):
        return None


def issued_before(claims: dict, moment: str | float) -> bool:
    """True when the token was issued before `moment` (a timestamp, e.g. when the password last changed)."""
    return float(claims.get("iatf", claims["iat"])) < float(moment)
