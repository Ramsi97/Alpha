"""Self-service data deletion (plan section 18: "Provide a simple
data-deletion path for users who ask").

Anonymizes PII and marks the row deleted; does not delete the row itself
or anything it's referenced by (scores, xp_events, ...) — same principle
already used for admin XP reversals (ledger rows are never deleted, only
ever added to) applied to personal data instead of financial-style data.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def delete_account(db: AsyncSession, user: User) -> None:
    user.username = None
    user.first_name = None
    user.last_name = None
    user.photo_url = None
    user.deleted_at = datetime.now(UTC)
    user.notifications_enabled = False
    await db.commit()
