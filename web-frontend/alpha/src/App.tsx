import { useState } from "react";
import { BottomNav } from "./components/BottomNav";
import { CatalogScreen } from "./screens/CatalogScreen";
import { GameScreen } from "./screens/GameScreen";
import { LeaderboardScreen } from "./screens/LeaderboardScreen";
import { ProfileScreen } from "./screens/ProfileScreen";
import { TasksScreen } from "./screens/TasksScreen";
import { AuthProvider, useAuth } from "./state/AuthContext";

export type View = "catalog" | "leaderboard" | "tasks" | "profile";

function Shell() {
  const { user, loading, error } = useAuth();
  const [view, setView] = useState<View>("catalog");
  const [playingSlug, setPlayingSlug] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="screen screen--centered">
        <div className="loading">Loading AlphaGo…</div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="screen screen--centered">
        <div className="banner banner--error">{error ?? "Could not sign you in."}</div>
      </div>
    );
  }

  if (playingSlug) {
    return <GameScreen slug={playingSlug} onBack={() => setPlayingSlug(null)} />;
  }

  return (
    <div className="app-shell">
      <div className="app-shell__content">
        {view === "catalog" && <CatalogScreen onPlay={setPlayingSlug} />}
        {view === "leaderboard" && <LeaderboardScreen />}
        {view === "tasks" && <TasksScreen />}
        {view === "profile" && <ProfileScreen />}
      </div>
      <BottomNav active={view} onChange={setView} />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
