"""Create (or reset) a super admin: the person who runs the whole platform.

    python -m scripts.create_platform_admin --name "Your Name" --email you@company.com
    (you will be asked for the password; or pass --password)
Inside Docker:  docker compose run --rm api python -m scripts.create_platform_admin --name "..." --email ...
Open http://localhost:8000/platform/ to sign in. Running it again with an existing email resets that password."""
import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.db import system_session
from app.core.security import hash_password
from app.models import PlatformAdmin, PlatformAudit


async def main(a: argparse.Namespace) -> None:
    pw = a.password or getpass.getpass("Password (at least 12 characters): ")
    if len(pw) < 12:
        sys.exit("The password must be at least 12 characters.")
    async with system_session() as s:
        admin = (await s.execute(select(PlatformAdmin).where(PlatformAdmin.email == a.email.lower()))).scalar_one_or_none()
        if admin:
            admin.password_hash, admin.is_active, admin.name = hash_password(pw), True, a.name
            what = "updated"
        else:
            s.add(PlatformAdmin(name=a.name, email=a.email.lower(), password_hash=hash_password(pw)))
            what = "created"
        s.add(PlatformAudit(admin_email="command line", action=f"admin.{what}", detail_json={"email": a.email.lower()}))
    print(f"Super admin {a.email.lower()} {what}. Sign in at /platform/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password")
    asyncio.run(main(p.parse_args()))
