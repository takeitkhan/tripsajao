"""Provision a tenant + first admin user (platform-operator tool; uses the BYPASSRLS system role).

    python -m scripts.create_tenant --name "Sunrise Resorts" --domain sunrise.example \
        --admin-email owner@sunrise.example --admin-password '...'
"""
import argparse
import asyncio

from app.core.constants import DEFAULT_API_CLIENT_SCOPES
from app.core.db import system_session
from app.core.security import generate_api_credentials, hash_api_secret, hash_password
from app.models import Role, Tenant, User


async def main(a: argparse.Namespace) -> None:
    key, secret = generate_api_credentials()
    async with system_session() as s:
        tenant = Tenant(name=a.name, domain=a.domain.lower(), api_key=key, api_secret_hash=hash_api_secret(secret),
                        api_scopes=DEFAULT_API_CLIENT_SCOPES,
                        settings_json={"timezone": a.timezone, "deposit_percent": 50, "hold_seconds": 600,
                                       "min_payout": 1000, "attribution_model": "last_click",
                                       "landing_path": "/", "property_path_template": "/properties/{slug}"})
        s.add(tenant)
        await s.flush()
        s.add(User(tenant_id=tenant.id, name="Owner", email=a.admin_email.lower(),
                   password_hash=hash_password(a.admin_password), role=Role.ADMIN))
    print(f"tenant_id : {tenant.id}\nX-API-KEY : {key}\nX-API-SECRET (store now, never shown again): {secret}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-password", required=True)
    p.add_argument("--timezone", default="UTC")
    asyncio.run(main(p.parse_args()))
