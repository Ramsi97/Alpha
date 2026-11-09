"""Notification worker (plan section 14.3).

Usage: python -m app.workers.notification_worker
Polls app.services.notifications.process_outbox once a second forever.
See that module's docstring for why this is a plain loop instead of ARQ.
"""

import asyncio
import logging

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.telegram_client import get_telegram_client
from app.services.notifications import process_outbox

logger = logging.getLogger(__name__)


async def main() -> None:
    telegram_client = get_telegram_client()
    while True:
        async with SessionLocal() as db:
            result = await process_outbox(db, telegram_client, settings.notify_rate_per_second)
        if result["considered"]:
            logger.info("notification_worker pass: %s", result)
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
