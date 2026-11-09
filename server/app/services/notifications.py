"""Notification outbox and worker (plan section 14.3).

The plan recommends ARQ (Redis-backed) for the worker process. This
environment has no real Redis (see app/core/redis.py), and ARQ's job queue
relies on Redis blocking-list semantics that fakeredis doesn't fully
replicate reliably enough to trust for this. process_outbox() below is a
plain polling function instead — correct queue semantics (status,
scheduled_at, attempts, backoff) without needing ARQ's specific
infrastructure. Wherever this deploys with real Redis, wrapping this same
function in an ARQ cron job is a small, low-risk change — the business
logic doesn't need to move.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram_client import TelegramClient
from app.models.notification import NotificationOutbox
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

# Afaan Oromo ("om") and Amharic ("am") strings below are a best-effort,
# non-native-reviewed pass (plan section 21/B5: "multi-language bot
# templates... Afaan Oromo, Amharic, English") — good enough to exercise
# the render_template/language-fallback mechanism end-to-end, but flag
# them for a native-speaker review before this ships to real users in
# either language. English is the one language actually verified by use.
TEMPLATES = {
    "new_task": {
        "en": "A new task is available! Open the app to check it out.",
        "am": "አዲስ ተግባር አለ! መተግበሪያውን ይክፈቱ እና ይመልከቱ።",
        "om": "Hojiin haaraa jira! Appii banii ilaali.",
    },
    "streak_reminder": {
        "en": "Don't lose your streak — check in today!",
        "am": "ተራዎን እንዳያጡ — ዛሬ ይግቡ!",
        "om": "Daldala kee hin dhabin — har'a seeni!",
    },
    "challenge_beaten": {
        "en": "Someone beat your challenge score. Rematch?",
        "am": "አንድ ሰው ነጥብዎን አልፎታል። መልሶ ይሞክሩ?",
        "om": "Namni tokko qabxii kee mo'ate. Deebi'ii yaali?",
    },
    "level_up": {
        "en": "You reached level {level}!",
        "am": "ወደ ደረጅት {level} ደርሰዋል!",
        "om": "Sadarkaa {level} gaheera!",
    },
    "season_end": {
        "en": "The season has ended — you finished rank #{rank}.",
        "am": "ወቅቱ አብቅቷል — በደረጅት #{rank} ጨርሰዋል።",
        "om": "Yeroon xumurameera — sadarkaa #{rank} irratti xumurte.",
    },
    "tournament_start": {
        "en": "A new tournament just started.",
        "am": "አዲስ ውድድር ጀምሯል።",
        "om": "Dorgommiin haaraa jalqabe.",
    },
    "tournament_end": {
        "en": "The tournament has ended — you finished rank #{rank}.",
        "am": "ውድድሩ አብቅቷል — በደረጅት #{rank} ጨርሰዋል።",
        "om": "Dorgommiin xumurameera — sadarkaa #{rank} irratti xumurte.",
    },
    "friend_joined": {
        "en": "A friend joined using your referral link!",
        "am": "ጓደኛዎ የግብዣ ማስፈንጠሪያዎን ተጠቅሞ ተቀላቅሏል!",
        "om": "Michuun kee link afeerraa kee fayyadamee seeneera!",
    },
}


def render_template(notif_type: str, payload: dict, language: str) -> str:
    templates = TEMPLATES.get(notif_type)
    if templates is None:
        return notif_type  # unknown type: fall back to something rather than crash
    text = templates.get(language) or templates["en"]
    try:
        return text.format(**payload)
    except (KeyError, IndexError):
        return text


def queue_notification(db: AsyncSession, user_id: int, notif_type: str, payload: dict | None = None) -> NotificationOutbox:
    row = NotificationOutbox(user_id=user_id, type=notif_type, payload=payload or {})
    db.add(row)
    return row


async def process_outbox(
    db: AsyncSession,
    telegram_client: TelegramClient,
    rate_per_second: int,
    batch_size: int = 500,
) -> dict:
    """One polling pass: sends up to `rate_per_second` messages (plan
    section 14.3's token bucket, simplified to "this many per call" since
    callers are expected to call this roughly once a second in a real
    worker loop), applying all of plan 14.3's per-outcome rules. Returns
    counts for observability."""
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(NotificationOutbox)
            .where(NotificationOutbox.status == "queued", NotificationOutbox.scheduled_at <= now)
            .order_by(NotificationOutbox.scheduled_at)
            .limit(batch_size)
        )
    ).scalars().all()

    sent = skipped = failed = deferred = 0
    budget = rate_per_second

    for row in rows:
        if budget <= 0:
            break

        user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
        if user is None or not user.notifications_enabled or user.bot_blocked:
            row.status = "skipped"
            skipped += 1
            continue

        text = render_template(row.type, row.payload, user.language)
        result = await telegram_client.send_message(user.telegram_id, text)
        budget -= 1

        if result.ok:
            row.status = "sent"
            row.sent_at = now
            sent += 1
        elif result.blocked:
            user.bot_blocked = True
            row.status = "skipped"
            skipped += 1
        elif result.retry_after is not None:
            # 429: leave status='queued', just push scheduled_at back —
            # plan section 14.3 point 3 ("wait for retry_after and retry").
            row.scheduled_at = now + timedelta(seconds=result.retry_after)
            row.attempts += 1
            deferred += 1
        else:
            row.attempts += 1
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                failed += 1
            else:
                row.scheduled_at = now + timedelta(seconds=2 ** row.attempts)  # simple backoff
                deferred += 1

    await db.commit()
    return {"sent": sent, "skipped": skipped, "failed": failed, "deferred": deferred, "considered": len(rows)}
