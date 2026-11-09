import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, loadStoredToken, setToken } from "../lib/api";
import { buildDevInitData, getInitData, initTelegramUi } from "../lib/telegram";
import type { UserOut } from "../lib/types";

interface AuthState {
  user: UserOut | null;
  loading: boolean;
  error: string | null;
  refreshMe: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshMe = useCallback(async () => {
    const me = await api.me();
    setUser(me);
  }, []);

  useEffect(() => {
    initTelegramUi();

    (async () => {
      try {
        const stored = loadStoredToken();
        if (stored) {
          try {
            setUser(await api.me());
            setLoading(false);
            return;
          } catch {
            setToken(null); // stale/expired — fall through to a fresh login
          }
        }

        let initData = getInitData();
        if (!initData) {
          if (import.meta.env.DEV) {
            // Not opened inside Telegram — sign a dev-only initData so the
            // app is still testable in a plain browser. See lib/telegram.ts.
            initData = await buildDevInitData("dev-placeholder-bot-token", 1000000001, "Dev");
          } else {
            throw new Error("This app must be opened from Telegram.");
          }
        }

        const auth = await api.authTelegram(initData);
        setToken(auth.access_token);
        setUser(auth.user);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Login failed.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, error, refreshMe, logout }), [user, loading, error, refreshMe, logout]);

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthState {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
