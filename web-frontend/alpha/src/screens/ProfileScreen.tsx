import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { CheckinStatus } from "../lib/types";
import { useAuth } from "../state/AuthContext";
// UserOut doesn't currently expose notifications_enabled back to the
// client (see app/schemas/user.py) — the toggle below is write-only
// until that's added; treat the button as "turn notifications off".

const LANGUAGES: { code: "en" | "am" | "om"; label: string }[] = [
  { code: "en", label: "English" },
  { code: "am", label: "አማርኛ" },
  { code: "om", label: "Afaan Oromoo" },
];

export function ProfileScreen() {
  const { user, refreshMe, logout } = useAuth();
  const [checkin, setCheckin] = useState<CheckinStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api.checkinStatus().then(setCheckin).catch(() => {});
  }, []);

  if (!user) return null;

  const progress = user.level_progress
    ? Math.min(100, Math.round((user.level_progress.current_level_xp / user.level_progress.xp_for_next_level) * 100))
    : 0;

  async function doCheckin() {
    setBusy(true);
    try {
      const result = await api.checkin();
      setCheckin(result);
      haptic("success");
      setNotice(`+${result.xp_awarded} XP · streak ${result.streak_count}`);
      await refreshMe();
    } catch {
      setNotice("Already checked in today.");
    } finally {
      setBusy(false);
    }
  }

  async function changeLanguage(lang: "en" | "am" | "om") {
    await api.patchMe({ language: lang });
    await refreshMe();
  }

  async function toggleNotifications() {
    await api.patchMe({ notifications_enabled: false }); // re-enabling requires a fresh Telegram auth (see server README)
    await refreshMe();
  }

  async function deleteAccount() {
    if (!confirm("Delete your AlphaGo data? This clears your profile info; your scores stay anonymized.")) return;
    await api.deleteMe();
    logout();
  }

  return (
    <div className="screen">
      <header className="screen__header">
        <h1>Profile</h1>
      </header>

      <div className="profile-card">
        <div className="profile-card__name">{user.first_name ?? user.username ?? `Player ${user.id}`}</div>
        <div className="profile-card__level">Level {user.level}</div>
        <div className="xp-bar">
          <div className="xp-bar__fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="profile-card__meta">{user.total_xp} total XP · {user.achievements_unlocked} achievements</div>
      </div>

      <div className="profile-card">
        <div className="profile-card__row">
          <span>Daily check-in</span>
          <button className="btn btn--small" disabled={busy || checkin?.checked_in_today} onClick={doCheckin}>
            {checkin?.checked_in_today ? "Done today" : "Check in"}
          </button>
        </div>
        <div className="profile-card__meta">🔥 {checkin?.streak_count ?? user.streak_count} day streak</div>
        {notice && <div className="profile-card__notice">{notice}</div>}
      </div>

      <div className="profile-card">
        <div className="profile-card__row">Language</div>
        <div className="segmented">
          {LANGUAGES.map((l) => (
            <button key={l.code} className={user.language === l.code ? "is-active" : ""} onClick={() => changeLanguage(l.code)}>
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <div className="profile-card">
        <button className="btn btn--secondary" onClick={toggleNotifications}>
          Disable notifications
        </button>
      </div>

      <div className="profile-card">
        <button className="btn btn--danger" onClick={deleteAccount}>
          Delete my data
        </button>
      </div>
    </div>
  );
}
