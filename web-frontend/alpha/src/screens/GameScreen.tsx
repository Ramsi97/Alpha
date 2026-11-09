import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { getThemeParams, getWebApp } from "../lib/telegram";
import type { GameDetailOut, SessionCreateResponse, SessionFinishResponse } from "../lib/types";
import { useAuth } from "../state/AuthContext";

// Host side of games/_shared/alphago-bridge.js's postMessage contract.
// See games/_tools/test-host.html for the reference implementation this
// mirrors (sandbox attrs, message shapes, "start" payload fields).

type Phase = "loading" | "playing" | "finished" | "error";

export function GameScreen({ slug, onBack }: { slug: string; onBack: () => void }) {
  const { refreshMe } = useAuth();
  const [game, setGame] = useState<GameDetailOut | null>(null);
  const [session, setSession] = useState<SessionCreateResponse | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [result, setResult] = useState<SessionFinishResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const gameOverHandled = useRef(false);

  // Telegram's own back button, when available; always render an on-screen
  // fallback too since this also needs to work in a plain dev browser.
  useEffect(() => {
    const webApp = getWebApp();
    webApp?.BackButton.show();
    webApp?.BackButton.onClick(onBack);
    return () => {
      webApp?.BackButton.hide();
      if (webApp) webApp.BackButton.offClick(onBack);
    };
  }, [onBack]);

  useEffect(() => {
    let cancelled = false;
    gameOverHandled.current = false;
    setPhase("loading");
    setResult(null);

    (async () => {
      try {
        const [gameDetail, newSession] = await Promise.all([api.getGame(slug), api.startSession(slug)]);
        if (cancelled) return;
        setGame(gameDetail);
        setSession(newSession);
        setPhase("playing");
      } catch (e) {
        if (!cancelled) {
          setErrorMsg(e instanceof Error ? e.message : "Could not start this game.");
          setPhase("error");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Heartbeat so the backend can track active play time independent of
  // the final score report (plan section 8.2's min_play_seconds check).
  useEffect(() => {
    if (phase !== "playing" || !session) return;
    const interval = setInterval(() => {
      api.heartbeat(session.session_id).catch(() => {});
    }, 20_000);
    return () => clearInterval(interval);
  }, [phase, session]);

  useEffect(() => {
    if (!session || !game) return;
    const activeSession = session;

    function sendToGame(msg: Record<string, unknown>) {
      iframeRef.current?.contentWindow?.postMessage({ source: "alphago-host", ...msg }, "*");
    }

    async function handleMessage(e: MessageEvent) {
      if (iframeRef.current && e.source !== iframeRef.current.contentWindow) return;
      const data = e.data ?? {};
      if (data.source !== "alphago-game") return;

      if (data.type === "ready") {
        sendToGame({ variant: activeSession.variant, seed: activeSession.seed, lang: "en", theme: getThemeParams(), type: "start" });
      } else if (data.type === "gameover" && !gameOverHandled.current) {
        gameOverHandled.current = true;
        const score = typeof data.score === "number" ? data.score : 0;
        try {
          const finishResult = await api.finishSession(activeSession.session_id, {
            token: activeSession.token,
            score,
            variant: activeSession.variant,
          });
          setResult(finishResult);
          setPhase("finished");
          await refreshMe();
        } catch (err) {
          setErrorMsg(err instanceof ApiError ? err.message : "Could not submit your score.");
          setPhase("error");
        }
      } else if (data.type === "error") {
        setErrorMsg(typeof data.message === "string" ? data.message : "The game reported an error.");
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [session, game, refreshMe]);

  async function playAgain() {
    try {
      setPhase("loading");
      const newSession = await api.startSession(slug);
      setSession(newSession);
      gameOverHandled.current = false;
      setResult(null);
      setPhase("playing");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Could not start a new run.");
      setPhase("error");
    }
  }

  if (phase === "error") {
    return (
      <div className="screen screen--centered">
        <div className="banner banner--error">{errorMsg}</div>
        <button className="btn" onClick={onBack}>
          Back to games
        </button>
      </div>
    );
  }

  return (
    <div className="screen game-screen">
      <header className="screen__header">
        <button className="btn-icon" onClick={onBack} aria-label="Back">
          ←
        </button>
        <h1>{game?.title.en ?? slug}</h1>
      </header>

      <div className="game-screen__frame-wrap">
        {phase === "loading" && <div className="loading">Loading…</div>}
        {game && session && (
          <iframe
            ref={iframeRef}
            key={session.session_id}
            src={game.entry_url}
            className="game-screen__frame"
            sandbox="allow-scripts allow-same-origin"
            title={game.title.en ?? slug}
          />
        )}
      </div>

      {phase === "finished" && result && (
        <div className="result-overlay">
          <div className="result-card">
            <h2>Run complete</h2>
            <p className="result-card__score">Score: {result.score}</p>
            <p>+{result.xp_awarded} XP {result.flagged && "(under review)"}</p>
            <p>Level {result.level}</p>
            {result.rank !== null && <p>Global rank: #{result.rank}</p>}
            {result.new_achievements.length > 0 && <p>🏅 New achievement{result.new_achievements.length > 1 ? "s" : ""}!</p>}
            <div className="result-card__actions">
              <button className="btn" onClick={playAgain}>
                Play again
              </button>
              <button className="btn btn--secondary" onClick={onBack}>
                Back to games
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
