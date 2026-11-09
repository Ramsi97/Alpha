import json
import logging
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.game import Game
from app.schemas.manifest import GameManifest

logger = logging.getLogger(__name__)


def _entry_url(slug: str, version: str, entry: str) -> str:
    # Production should use versioned immutable paths once real CDN hosting
    # exists (plan section 4: `/{slug}/{version}/index.html`). Locally,
    # games/_tools/test-host.html serves them unversioned straight from
    # games/<slug>/, so that's what this points at for now.
    return f"{settings.games_origin}/{slug}/{entry}"


def _thumbnail_url(slug: str, thumbnail: str) -> str:
    # Same games_origin resolution as _entry_url — manifest.thumbnail is a
    # bare filename (e.g. "thumb.svg") relative to games/<slug>/, which the
    # API's own origin can't serve; a client needs an absolute URL just
    # like entry_url. Found via the web-frontend catalog screen rendering
    # broken <img> tags for every game.
    return f"{settings.games_origin}/{slug}/{thumbnail}"


# "dummy" is games/_tools/test-host.html's own fixture for proving the bridge
# works (plan Phase G0) — never meant to be a catalog entry (see its own
# CREDITS.md: "not shipped").
_EXCLUDED_SLUGS = {"dummy"}


def find_manifests(games_dir: Path) -> list[Path]:
    found = []
    for child in sorted(games_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_") or child.name in _EXCLUDED_SLUGS:
            continue
        manifest_path = child / "game.json"
        if manifest_path.exists():
            found.append(manifest_path)
    return found


async def import_manifest_file(db: AsyncSession, manifest_path: Path) -> dict:
    slug_from_dir = manifest_path.parent.name
    try:
        raw = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        return {"slug": slug_from_dir, "ok": False, "error": f"invalid JSON: {e}"}

    try:
        manifest = GameManifest.model_validate(raw)
    except ValidationError as e:
        return {"slug": slug_from_dir, "ok": False, "error": f"schema validation failed: {e}"}

    if manifest.slug != slug_from_dir:
        return {
            "slug": slug_from_dir,
            "ok": False,
            "error": f"manifest slug '{manifest.slug}' does not match folder name '{slug_from_dir}'",
        }
    if not manifest.license.code:
        return {"slug": slug_from_dir, "ok": False, "error": "license.code is required"}

    existing = (await db.execute(select(Game).where(Game.slug == manifest.slug))).scalar_one_or_none()
    entry_url = _entry_url(manifest.slug, manifest.version, manifest.entry)
    thumbnail_url = _thumbnail_url(manifest.slug, manifest.thumbnail)

    if existing is None:
        game = Game(
            slug=manifest.slug,
            version=manifest.version,
            title=manifest.title,
            description=manifest.description,
            category=manifest.category,
            thumbnail_url=thumbnail_url,
            entry_url=entry_url,
            variants=manifest.variants,
            max_score=int(manifest.score.max_score),
            min_play_seconds=int(manifest.score.min_play_seconds),
            max_score_per_second=manifest.score.max_score_per_second,
            xp_rate=manifest.xp.rate,
            max_xp_per_run=int(manifest.xp.max_per_run),
            license_code=manifest.license.code,
            license_assets=manifest.license.assets,
            author=manifest.license.author,
            source_url=manifest.license.source_url,
            size_kb=int(manifest.size_kb),
            status="pending",  # new games always arrive pending; an admin activates them (plan section 7)
        )
        db.add(game)
        action = "created"
    else:
        existing.version = manifest.version
        existing.title = manifest.title
        existing.description = manifest.description
        existing.category = manifest.category
        existing.thumbnail_url = thumbnail_url
        existing.entry_url = entry_url
        existing.variants = manifest.variants
        existing.max_score = int(manifest.score.max_score)
        existing.min_play_seconds = int(manifest.score.min_play_seconds)
        existing.max_score_per_second = manifest.score.max_score_per_second
        existing.xp_rate = manifest.xp.rate
        existing.max_xp_per_run = int(manifest.xp.max_per_run)
        existing.license_code = manifest.license.code
        existing.license_assets = manifest.license.assets
        existing.author = manifest.license.author
        existing.source_url = manifest.license.source_url
        existing.size_kb = int(manifest.size_kb)
        # status is intentionally left untouched on update — re-importing a
        # manifest for an already-`active` game must not silently deactivate it.
        action = "updated"

    return {"slug": manifest.slug, "ok": True, "action": action}


async def import_all_manifests(db: AsyncSession, games_dir: Path) -> list[dict]:
    results = []
    for manifest_path in find_manifests(games_dir):
        result = await import_manifest_file(db, manifest_path)
        results.append(result)
    await db.commit()
    return results
