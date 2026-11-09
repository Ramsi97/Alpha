"""Reader for the `settings` table (plan section 2 principle 4: tunable
values live in the database, not in code). Named settings_store to avoid
clashing with app.core.config.settings (the env-var Settings instance)."""

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting

T = TypeVar("T")


async def get_setting(db: AsyncSession, key: str, default: T) -> T:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        return default
    return row.value  # JSONB — already the right Python type (dict/list/number/str)
