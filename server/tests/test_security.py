import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.core.security import InitDataError, validate_init_data

BOT_TOKEN = "test-bot-token-123"


def make_init_data(auth_date=None, tamper=False, bad_hash=False):
    auth_date = auth_date if auth_date is not None else int(time.time())
    user = json.dumps({"id": 42, "first_name": "Test", "username": "tester", "language_code": "en"})
    pairs = {"auth_date": str(auth_date), "user": user, "start_param": "r_abc123"}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        pairs["user"] = json.dumps({"id": 999, "first_name": "Evil"})
    full = dict(pairs)
    full["hash"] = "deadbeef" if bad_hash else h
    return urlencode(full)


def test_valid_init_data_parses_user_and_start_param():
    result = validate_init_data(make_init_data(), BOT_TOKEN, 86400)
    assert result["user"]["id"] == 42
    assert result["start_param"] == "r_abc123"


def test_tampered_payload_rejected():
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(tamper=True), BOT_TOKEN, 86400)


def test_bad_hash_rejected():
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(bad_hash=True), BOT_TOKEN, 86400)


def test_stale_auth_date_rejected():
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(auth_date=int(time.time()) - 100_000), BOT_TOKEN, 86400)


def test_wrong_bot_token_rejected():
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(), "a-different-bot-token", 86400)


def test_missing_hash_rejected():
    with pytest.raises(InitDataError):
        validate_init_data("auth_date=123&user=%7B%7D", BOT_TOKEN, 86400)
