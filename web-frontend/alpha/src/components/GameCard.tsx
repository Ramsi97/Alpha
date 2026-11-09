import type { GameOut } from "../lib/types";

export function GameCard({ game, onPlay, onToggleFavorite }: {
  game: GameOut;
  onPlay: () => void;
  onToggleFavorite: () => void;
}) {
  const title = game.title.en ?? Object.values(game.title)[0] ?? game.slug;

  return (
    <div className="game-card" onClick={onPlay}>
      <div className="game-card__thumb">
        {game.thumbnail_url ? (
          <img src={game.thumbnail_url} alt={title} loading="lazy" />
        ) : (
          <span className="game-card__thumb-fallback">{title.slice(0, 1)}</span>
        )}
        <button
          className={`game-card__fav ${game.is_favorite ? "is-active" : ""}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite();
          }}
          aria-label="Toggle favorite"
        >
          {game.is_favorite ? "★" : "☆"}
        </button>
      </div>
      <div className="game-card__title">{title}</div>
      <div className="game-card__meta">
        {game.best_score !== null ? `Best ${game.best_score}` : "Not played yet"}
        {game.average_rating !== null ? ` · ★${game.average_rating.toFixed(1)}` : ""}
      </div>
    </div>
  );
}
