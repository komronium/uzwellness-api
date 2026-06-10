"""Mark confirmed bookings with a past check_out as completed.

Usage (daily cron):
    uv run python -m scripts.complete_bookings
"""

import asyncio

from app.core.database import SessionLocal
from app.services.booking_service import complete_past_bookings


async def main() -> None:
    async with SessionLocal() as db:
        count = await complete_past_bookings(db)
    print(f"Completed {count} booking(s)")


if __name__ == "__main__":
    asyncio.run(main())
