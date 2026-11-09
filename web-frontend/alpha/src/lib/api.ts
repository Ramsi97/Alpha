import type {
  AuthResponse,
  CheckinResult,
  CheckinStatus,
  GameDetailOut,
  GameOut,
  LeaderboardOut,
  SessionCreateResponse,
  SessionFinishResponse,
  TaskOut,
  UserOut,
  VerifyResultOut,
} from "./types";

const API_BASE = `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/v1`;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let token: string | null = null;

export function setToken(value: string | null): void {
  token = value;
  if (value) localStorage.setItem("alphago_token", value);
  else localStorage.removeItem("alphago_token");
}

export function loadStoredToken(): string | null {
  token = localStorage.getItem("alphago_token");
  return token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, data.error ?? "unknown_error", data.message ?? res.statusText);
  }
  return data as T;
}

export const api = {
  authTelegram: (initData: string) => request<AuthResponse>("POST", "/auth/telegram", { init_data: initData }),

  me: () => request<UserOut>("GET", "/me"),
  patchMe: (body: { language?: string; notifications_enabled?: boolean }) => request<UserOut>("PATCH", "/me", body),
  deleteMe: () => request<void>("DELETE", "/me"),

  listGames: (opts?: { category?: string; sortBy?: "default" | "trending" }) => {
    const qs = new URLSearchParams();
    if (opts?.category) qs.set("category", opts.category);
    if (opts?.sortBy) qs.set("sort_by", opts.sortBy);
    const query = qs.toString();
    return request<GameOut[]>("GET", `/games${query ? `?${query}` : ""}`);
  },
  getGame: (slug: string) => request<GameDetailOut>("GET", `/games/${slug}`),
  favoriteGame: (slug: string) => request<void>("POST", `/games/${slug}/favorite`),
  unfavoriteGame: (slug: string) => request<void>("DELETE", `/games/${slug}/favorite`),
  rateGame: (slug: string, rating: number) => request<void>("POST", `/games/${slug}/rating`, { rating }),

  startSession: (slug: string, variant?: string | null) =>
    request<SessionCreateResponse>("POST", `/games/${slug}/sessions`, { variant: variant ?? null }),
  heartbeat: (sessionId: string) => request<{ active_seconds: number }>("POST", `/sessions/${sessionId}/heartbeat`),
  finishSession: (sessionId: string, body: { token: string; score: number; variant?: string | null; meta?: unknown }) =>
    request<SessionFinishResponse>("POST", `/sessions/${sessionId}/finish`, body),

  leaderboardXp: () => request<LeaderboardOut>("GET", "/leaderboards/xp"),
  leaderboardGame: (slug: string, variant?: string | null) =>
    request<LeaderboardOut>("GET", `/leaderboards/games/${slug}${variant ? `?variant=${variant}` : ""}`),
  leaderboardFriends: () => request<LeaderboardOut>("GET", "/leaderboards/friends"),
  leaderboardSeason: () => request<LeaderboardOut>("GET", "/leaderboards/season"),

  listTasks: () => request<TaskOut[]>("GET", "/tasks"),
  startTask: (taskId: number) => request<{ task_id: number; period_key: string; status: string; payload: unknown }>(
    "POST",
    `/tasks/${taskId}/start`,
  ),
  verifyTask: (taskId: number) => request<VerifyResultOut>("POST", `/tasks/${taskId}/verify`),

  checkinStatus: () => request<CheckinStatus>("GET", "/checkin"),
  checkin: () => request<CheckinResult>("POST", "/checkin"),
};
