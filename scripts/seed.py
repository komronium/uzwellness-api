"""Seed production super_admin from env vars. Idempotent: safe to re-run.

Usage:
    uv run python -m scripts.seed
"""

import asyncio
import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.services.user_service import UserService


async def seed_super_admin() -> None:
    email = settings.INITIAL_SUPER_ADMIN_EMAIL
    password = settings.INITIAL_SUPER_ADMIN_PASSWORD
    if not email or not password:
        print(
            "Skip super_admin seed: set INITIAL_SUPER_ADMIN_EMAIL and "
            "INITIAL_SUPER_ADMIN_PASSWORD in .env",
            file=sys.stderr,
        )
        return

    async with SessionLocal() as db:
        users = UserService(db)
        existing = await users.get_by_email(email)
        if existing is not None:
            if existing.role != UserRole.SUPER_ADMIN:
                existing.role = UserRole.SUPER_ADMIN
                await db.commit()
                print(f"Promoted {email} to super_admin")
            else:
                print(f"super_admin already exists: {email}")
            return

        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            role=UserRole.SUPER_ADMIN,
            full_name="Super Admin",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"Created super_admin: {email}")


async def main() -> None:
    await seed_super_admin()


if __name__ == "__main__":
    asyncio.run(main())
