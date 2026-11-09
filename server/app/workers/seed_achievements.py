"""Seeds the first ~10 achievements (plan section 11/B2).

Usage: python -m app.workers.seed_achievements
Idempotent: upserts by `key`, safe to re-run.
"""

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.achievement import Achievement

ACHIEVEMENTS = [
    dict(
        key="first_run", title={"en": "First Steps"},
        description={"en": "Complete your first game run."},
        icon="🎮", condition={"type": "total_runs", "value": 1}, xp_reward=20,
    ),
    dict(
        key="ten_runs", title={"en": "Getting Started"},
        description={"en": "Complete 10 game runs."},
        icon="🔥", condition={"type": "total_runs", "value": 10}, xp_reward=50,
    ),
    dict(
        key="hundred_runs", title={"en": "Dedicated Player"},
        description={"en": "Complete 100 game runs."},
        icon="💯", condition={"type": "total_runs", "value": 100}, xp_reward=200,
    ),
    dict(
        key="streak_3", title={"en": "Three in a Row"},
        description={"en": "Check in 3 days in a row."},
        icon="📅", condition={"type": "streak", "value": 3}, xp_reward=20,
    ),
    dict(
        key="streak_7", title={"en": "One Week Strong"},
        description={"en": "Check in 7 days in a row."},
        icon="🗓️", condition={"type": "streak", "value": 7}, xp_reward=75,
    ),
    dict(
        key="streak_30", title={"en": "Habit Formed"},
        description={"en": "Check in 30 days in a row."},
        icon="🏆", condition={"type": "streak", "value": 30}, xp_reward=300,
    ),
    dict(
        key="level_5", title={"en": "Rising Star"},
        description={"en": "Reach level 5."},
        icon="⭐", condition={"type": "level", "value": 5}, xp_reward=0,
    ),
    dict(
        key="level_10", title={"en": "Seasoned Player"},
        description={"en": "Reach level 10."},
        icon="🌟", condition={"type": "level", "value": 10}, xp_reward=0,
    ),
    dict(
        key="level_20", title={"en": "Veteran"},
        description={"en": "Reach level 20."},
        icon="💫", condition={"type": "level", "value": 20}, xp_reward=0,
    ),
    dict(
        key="score_2048_5000", title={"en": "2048 Specialist"},
        description={"en": "Score at least 5000 in 2048."},
        icon="🔢", condition={"type": "score_at_least", "game": "2048", "value": 5000}, xp_reward=30,
    ),
]


async def seed() -> None:
    async with SessionLocal() as db:
        for data in ACHIEVEMENTS:
            existing = (await db.execute(select(Achievement).where(Achievement.key == data["key"]))).scalar_one_or_none()
            if existing is None:
                db.add(Achievement(**data))
                print(f"created {data['key']}")
            else:
                for field, value in data.items():
                    setattr(existing, field, value)
                print(f"updated {data['key']}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
