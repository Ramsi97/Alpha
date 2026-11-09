"""Score-card image generation (plan section 15: POST /share/score-card).

Cached by content hash on disk: the same (user, game, variant, score)
always maps to the same file, so repeat shares of an already-rendered
result are a free lookup instead of a re-render.
"""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.game import Game
from app.models.user import User

CARD_SIZE = (1200, 630)
BACKGROUND = (24, 28, 38)
ACCENT = (88, 166, 255)
TEXT = (235, 238, 245)
MUTED = (150, 158, 176)


def _score_cards_dir() -> Path:
    path = Path(settings.media_dir) / "score_cards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(user_id: int, game_id: int, variant: str | None, score: int) -> str:
    raw = f"{user_id}:{game_id}:{variant or ''}:{score}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _render(path: Path, title: str, player_name: str, score: int, variant: str | None) -> None:
    img = Image.new("RGB", CARD_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(img)
    font_big = ImageFont.load_default(size=72)
    font_mid = ImageFont.load_default(size=40)
    font_small = ImageFont.load_default(size=28)

    draw.text((60, 60), "AlphaGo", font=font_small, fill=ACCENT)
    draw.text((60, 150), title, font=font_mid, fill=TEXT)
    draw.text((60, 230), f"{score:,}", font=font_big, fill=ACCENT)
    subtitle = f"{player_name} · {variant}" if variant else player_name
    draw.text((60, 340), subtitle, font=font_small, fill=MUTED)

    img.save(path, format="PNG")


async def build_score_card(db: AsyncSession, user: User, game_slug: str, variant: str | None, score: int) -> str:
    game = (await db.execute(select(Game).where(Game.slug == game_slug))).scalar_one_or_none()
    if game is None:
        raise ValueError(f"No game with slug '{game_slug}'.")

    key = _cache_key(user.id, game.id, variant, score)
    rel_path = f"score_cards/{key}.png"
    file_path = _score_cards_dir() / f"{key}.png"

    if not file_path.exists():
        title = game.title.get("en", game_slug) if isinstance(game.title, dict) else str(game.title)
        player_name = user.first_name or user.username or f"Player {user.id}"
        _render(file_path, title, player_name, score, variant)

    return f"{settings.public_base_url}/media/{rel_path}"
