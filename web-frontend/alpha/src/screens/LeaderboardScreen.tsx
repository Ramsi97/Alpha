import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { LeaderboardOut } from "../lib/types";

type Tab = "xp" | "friends" | "season";

const FETCHERS: Record<Tab, () => Promise<LeaderboardOut>> = {
  xp: api.leaderboardXp,
  friends: api.leaderboardFriends,
  season: api.leaderboardSeason,
};

export function LeaderboardScreen() {
  const [tab, setTab] = useState<Tab>("xp");
  const [board, setBoard] = useState<LeaderboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBoard(null);
    setError(null);
    FETCHERS[tab]()
      .then((data) => !cancelled && setBoard(data))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "No leaderboard available."));
    return () => {
      cancelled = true;
    };
  }, [tab]);

  return (
    <div className="screen">
      <header className="screen__header">
        <h1>Leaderboard</h1>
      </header>

      <div className="segmented">
        <button className={tab === "xp" ? "is-active" : ""} onClick={() => setTab("xp")}>
          Global
        </button>
        <button className={tab === "friends" ? "is-active" : ""} onClick={() => setTab("friends")}>
          Friends
        </button>
        <button className={tab === "season" ? "is-active" : ""} onClick={() => setTab("season")}>
          Season
        </button>
      </div>

      {error && <div className="banner banner--error">{error}</div>}
      {!board && !error && <div className="loading">Loading…</div>}

      {board && (
        <>
          {board.my_rank !== null && (
            <div className="leaderboard__me">
              Your rank: #{board.my_rank} · {board.my_score} XP
            </div>
          )}
          <ol className="leaderboard-list">
            {board.entries.map((entry) => (
              <li key={entry.user_id} className="leaderboard-list__row">
                <span className="leaderboard-list__rank">#{entry.rank}</span>
                <span className="leaderboard-list__name">{entry.first_name ?? entry.username ?? `User ${entry.user_id}`}</span>
                <span className="leaderboard-list__score">{entry.score}</span>
              </li>
            ))}
            {board.entries.length === 0 && <div className="loading">No entries yet.</div>}
          </ol>
        </>
      )}
    </div>
  );
}
