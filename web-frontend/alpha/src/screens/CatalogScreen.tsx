import { useEffect, useState } from "react";
import { GameCard } from "../components/GameCard";
import { api } from "../lib/api";
import type { GameOut } from "../lib/types";

export function CatalogScreen({ onPlay }: { onPlay: (slug: string) => void }) {
  const [games, setGames] = useState<GameOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"default" | "trending">("default");

  useEffect(() => {
    let cancelled = false;
    setGames(null);
    api
      .listGames({ sortBy })
      .then((data) => {
        if (!cancelled) setGames(data);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load games."));
    return () => {
      cancelled = true;
    };
  }, [sortBy]);

  async function toggleFavorite(game: GameOut) {
    if (!games) return;
    const next = game.is_favorite ? api.unfavoriteGame(game.slug) : api.favoriteGame(game.slug);
    setGames(games.map((g) => (g.slug === game.slug ? { ...g, is_favorite: !g.is_favorite } : g)));
    try {
      await next;
    } catch {
      setGames(games); // revert optimistic update on failure
    }
  }

  return (
    <div className="screen">
      <header className="screen__header">
        <h1>AlphaGo</h1>
        <div className="segmented">
          <button className={sortBy === "default" ? "is-active" : ""} onClick={() => setSortBy("default")}>
            All
          </button>
          <button className={sortBy === "trending" ? "is-active" : ""} onClick={() => setSortBy("trending")}>
            Trending
          </button>
        </div>
      </header>

      {error && <div className="banner banner--error">{error}</div>}
      {!games && !error && <div className="loading">Loading games…</div>}

      {games && (
        <div className="game-grid">
          {games.map((game) => (
            <GameCard key={game.slug} game={game} onPlay={() => onPlay(game.slug)} onToggleFavorite={() => toggleFavorite(game)} />
          ))}
          {games.length === 0 && <div className="loading">No games yet.</div>}
        </div>
      )}
    </div>
  );
}
