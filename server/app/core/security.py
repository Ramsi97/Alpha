import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import jwt

from app.core.config import settings


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int) -> dict:
    """Validate a Telegram Mini App `initData` string per plan section 5.1.

    Returns {"user": {...}, "start_param": str | None} on success, raises
    InitDataError otherwise.
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("bad signature")

    try:
        auth_date = int(pairs.get("auth_date", 0))
    except ValueError as e:
        raise InitDataError("invalid auth_date") from e
    if time.time() - auth_date > max_age:
        raise InitDataError("initData too old")

    try:
        user = json.loads(pairs["user"])
    except (KeyError, json.JSONDecodeError) as e:
        raise InitDataError("missing or invalid user field") from e

    return {"user": user, "start_param": pairs.get("start_param")}


def issue_jwt(user_id: int, telegram_id: int) -> tuple[str, int]:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, settings.jwt_ttl_seconds


class TokenError(ValueError):
    pass


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("invalid token") from e
