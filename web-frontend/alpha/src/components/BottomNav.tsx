import type { View } from "../App";

const TABS: { view: View; label: string; icon: string }[] = [
  { view: "catalog", label: "Play", icon: "🎮" },
  { view: "leaderboard", label: "Ranks", icon: "🏆" },
  { view: "tasks", label: "Tasks", icon: "✅" },
  { view: "profile", label: "Profile", icon: "👤" },
];

export function BottomNav({ active, onChange }: { active: View; onChange: (v: View) => void }) {
  return (
    <nav className="bottom-nav">
      {TABS.map((tab) => (
        <button
          key={tab.view}
          className={`bottom-nav__tab ${active === tab.view ? "is-active" : ""}`}
          onClick={() => onChange(tab.view)}
        >
          <span className="bottom-nav__icon">{tab.icon}</span>
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
