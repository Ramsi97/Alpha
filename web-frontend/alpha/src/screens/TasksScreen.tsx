import { useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import type { TaskOut } from "../lib/types";
import { useAuth } from "../state/AuthContext";

export function TasksScreen() {
  const { refreshMe } = useAuth();
  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  function load() {
    api
      .listTasks()
      .then(setTasks)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load tasks."));
  }

  useEffect(load, []);

  async function handleAction(task: TaskOut) {
    setBusyId(task.id);
    setError(null);
    try {
      if (task.status === null) {
        await api.startTask(task.id);
      } else {
        const result = await api.verifyTask(task.id);
        if (result.status === "completed" || result.status === "pending_review") {
          await refreshMe();
        }
      }
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusyId(null);
    }
  }

  function actionLabel(task: TaskOut): string {
    if (task.status === "completed") return "Done";
    if (task.status === "pending_review") return "Pending review";
    if (task.status === "rejected") return "Rejected";
    if (task.status === "in_progress") return "Verify";
    return "Start";
  }

  return (
    <div className="screen">
      <header className="screen__header">
        <h1>Tasks</h1>
      </header>

      {error && <div className="banner banner--error">{error}</div>}
      {!tasks && !error && <div className="loading">Loading…</div>}

      {tasks && (
        <div className="task-list">
          {tasks.map((task) => {
            const done = task.status === "completed" || task.status === "pending_review" || task.status === "rejected";
            return (
              <div key={task.id} className="task-card">
                <div>
                  <div className="task-card__title">{task.title.en ?? Object.values(task.title)[0]}</div>
                  <div className="task-card__meta">+{task.xp_reward} XP · {task.period}</div>
                </div>
                <button className="btn btn--small" disabled={done || busyId === task.id} onClick={() => handleAction(task)}>
                  {busyId === task.id ? "…" : actionLabel(task)}
                </button>
              </div>
            );
          })}
          {tasks.length === 0 && <div className="loading">No tasks right now.</div>}
        </div>
      )}
    </div>
  );
}
