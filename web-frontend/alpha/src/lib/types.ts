// Mirrors server/app/schemas/*.py response shapes. Keep in sync by hand —
// there's no shared schema generation between the two repos yet.

export interface LevelProgress {
  current_level_xp: number;
  xp_for_next_level: number;
}

export interface UserOut {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  language: string;
  total_xp: number;
  level: number;
  streak_count: number;
  last_checkin_date: string | null;
  referral_code: string;
  level_progress: LevelProgress | null;
  achievements_unlocked: number;
}

export interface AuthResponse {
  access_token: string;
  expires_in: number;
  user: UserOut;
}

export interface GameOut {
  slug: string;
  version: string;
  title: Record<string, string>;
  description: Record<string, string> | null;
  category: string;
  thumbnail_url: string | null;
  entry_url: string;
  variants: string[];
  max_score: number;
  min_play_seconds: number;
  xp_rate: number;
  max_xp_per_run: number;
  max_score_per_second: number;
  status: string;
  best_score: number | null;
  is_favorite: boolean;
  recently_played: boolean;
  average_rating: number | null;
}

export interface GameDetailOut extends GameOut {
  license_code: string | null;
  license_assets: string | null;
  author: string | null;
  source_url: string | null;
}

export interface SessionCreateResponse {
  session_id: string;
  token: string;
  seed: string;
  variant: string | null;
}

export interface SessionFinishResponse {
  score: number;
  xp_awarded: number;
  total_xp: number;
  level: number;
  level_progress: LevelProgress;
  personal_best: number;
  rank: number | null;
  new_achievements: string[];
  flagged: boolean;
}

export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  username: string | null;
  first_name: string | null;
  score: number;
}

export interface LeaderboardOut {
  entries: LeaderboardEntry[];
  my_rank: number | null;
  my_score: number | null;
}

export interface TaskOut {
  id: number;
  type: string;
  title: Record<string, string>;
  description: Record<string, string> | null;
  xp_reward: number;
  period: string;
  verify_method: string;
  status: string | null;
}

export interface VerifyResultOut {
  status: string;
  xp_awarded: number;
}

export interface CheckinStatus {
  checked_in_today: boolean;
  streak_count: number;
  streak_freezes: number;
  last_checkin_date: string | null;
}

export interface CheckinResult extends CheckinStatus {
  xp_awarded: number;
  total_xp: number;
  level: number;
  new_achievements: string[];
}

export interface ApiErrorBody {
  error: string;
  message: string;
}
