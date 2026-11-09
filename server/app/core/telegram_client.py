"""Thin wrapper over the Telegram Bot API, used by task verification
(`join_channel`) and the notification worker.

No real BOT_TOKEN exists in this environment, so RealTelegramClient is
written to the documented Bot API shape but has **not been exercised
against the real API**. Tests use FakeTelegramClient. Swap which one
get_telegram_client() returns once a real bot token is configured.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings


@dataclass
class SendResult:
    ok: bool
    blocked: bool = False       # True on Telegram 403 "bot was blocked by the user"
    retry_after: int | None = None  # set on Telegram 429


class TelegramClient(Protocol):
    async def get_chat_member_status(self, chat_id: str, user_id: int) -> str | None:
        """One of Telegram's chat member statuses ('creator', 'administrator',
        'member', 'restricted', 'left', 'kicked'), or None if the lookup
        itself failed (bot not an admin of the chat, chat not found, etc.)."""
        ...

    async def send_message(self, chat_id: int, text: str) -> SendResult: ...


class RealTelegramClient:
    BASE_URL = "https://api.telegram.org"

    def __init__(self, bot_token: str):
        self._bot_token = bot_token

    async def get_chat_member_status(self, chat_id: str, user_id: int) -> str | None:
        url = f"{self.BASE_URL}/bot{self._bot_token}/getChatMember"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"chat_id": chat_id, "user_id": user_id})
        data = resp.json()
        if not data.get("ok"):
            return None
        return data["result"]["status"]

    async def send_message(self, chat_id: int, text: str) -> SendResult:
        url = f"{self.BASE_URL}/bot{self._bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        if resp.status_code == 200:
            return SendResult(ok=True)
        if resp.status_code == 429:
            retry_after = resp.json().get("parameters", {}).get("retry_after", 1)
            return SendResult(ok=False, retry_after=retry_after)
        if resp.status_code == 403:
            return SendResult(ok=False, blocked=True)
        return SendResult(ok=False)


class FakeTelegramClient:
    """Test double. Configure canned responses directly on the instance."""

    def __init__(self):
        self.chat_member_statuses: dict[tuple[str, int], str] = {}
        self.sent_messages: list[tuple[int, str]] = []
        self.send_results: dict[int, SendResult] = {}  # chat_id -> canned SendResult

    async def get_chat_member_status(self, chat_id: str, user_id: int) -> str | None:
        return self.chat_member_statuses.get((chat_id, user_id))

    async def send_message(self, chat_id: int, text: str) -> SendResult:
        if chat_id in self.send_results:
            return self.send_results[chat_id]
        self.sent_messages.append((chat_id, text))
        return SendResult(ok=True)


@lru_cache
def get_telegram_client() -> TelegramClient:
    return RealTelegramClient(settings.bot_token)
