"""Manifest import job (plan section 7).

Usage: python -m app.workers.import_manifests [games_dir]
Defaults to ../games relative to the server/ directory (this repo's layout).
"""

import asyncio
import sys
from pathlib import Path

from app.core.db import SessionLocal
from app.services.game_import import import_all_manifests

DEFAULT_GAMES_DIR = Path(__file__).resolve().parents[3] / "games"


async def main(games_dir: Path) -> None:
    async with SessionLocal() as db:
        results = await import_all_manifests(db, games_dir)
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    for r in ok:
        print(f"OK      {r['slug']:<16} {r['action']}")
    for r in failed:
        print(f"FAILED  {r['slug']:<16} {r['error']}")
    print(f"\n{len(ok)}/{len(results)} manifests imported.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    games_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GAMES_DIR
    asyncio.run(main(games_dir))
