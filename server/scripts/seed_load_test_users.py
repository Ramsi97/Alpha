"""Pre-creates N real users and mints valid JWTs for them directly
(bypassing POST /auth/telegram's per-IP rate limit, which a load
generator running from one IP would otherwise hit immediately and which
isn't the thing this particular test is trying to measure — the plan's
own traffic estimate for section 20 is dominated by already-authenticated
reads, not auth calls).

Usage: python -m scripts.seed_load_test_users [count]
Writes tokens to /tmp/load_test_tokens.json for scripts/locustfile.py to
read in on_start.
"""

import asyncio
import json
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import issue_jwt
from app.models.user import User
from app.services.auth import get_or_create_user

TOKENS_FILE = "/tmp/load_test_tokens.json"


async def seed(count: int) -> None:
    tokens = []
    async with SessionLocal() as db:
        for i in range(count):
            telegram_id = 900_000_000 + i
            existing = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if existing is None:
                user = await get_or_create_user(db, {"id": telegram_id, "first_name": f"Load{i}"}, None)
                await db.commit()
            else:
                user = existing
            token, _ = issue_jwt(user.id, user.telegram_id)
            tokens.append(token)

    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)
    print(f"wrote {len(tokens)} tokens to {TOKENS_FILE}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    asyncio.run(seed(n))
