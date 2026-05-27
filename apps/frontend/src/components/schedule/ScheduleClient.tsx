
import { useCallback, useEffect, useState } from "react";

interface ScheduledPost {
  id: number;
  job_id: string;
  reel_id: string;
  platform: string;
  title: string;
  description: string;
  tags: string[];
  visibility: string;
  publish_at: string;
  status: string;
  external_video_id: string | null;
  external_url: string | null;
  error_message: string | null;
  attempts: number;
  last_attempt_at: string | null;
  notify_subscribers: boolean;
  created_at: string;
  updated_at: string;
}

type FilterStatus = "all" | "pending" | "uploading" | "done" | "error" | "cancelled";

const STATUS_LABELS: Record<string, string> = {
  pending: "в очереди",
  uploading: "загружается",
  done: "опубликовано",
  error: "ошибка",
  cancelled: "отменено",
};

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube Shorts",
  instagram: "Instagram Reels",
};

export function ScheduleClient() {
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const qs = filter === "all" ? "" : `?status=${filter}`;
      const resp = await fetch(`/api/v1/schedule${qs}`, { cache: "no-store" });
      if (resp.ok) {
        setPosts((await resp.json()) as ScheduledPost[]);
        setError(null);
      } else {
        setError(`${resp.status} ${resp.statusText}`);
      }
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
    // Polling только пока вкладка видна — иначе лишние запросы для
    // пользователей которые открыли расписание и ушли в другие приложения.
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 15000);
    return () => clearInterval(interval);
  }, [refresh]);

  async function handleCancel(postId: number) {
    if (!confirm("Отменить публикацию?")) return;
    await fetch(`/api/v1/schedule/${postId}`, { method: "DELETE" });
    await refresh();
  }

  const counts = countByStatus(posts);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            { k: "all", label: `Все (${posts.length})` },
            { k: "pending", label: `В очереди (${counts.pending})` },
            { k: "uploading", label: `Загружаются (${counts.uploading})` },
            { k: "done", label: `Готово (${counts.done})` },
            { k: "error", label: `Ошибки (${counts.error})` },
            { k: "cancelled", label: `Отменены (${counts.cancelled})` },
          ] as const
        ).map((opt) => (
          <button
            key={opt.k}
            type="button"
            onClick={() => setFilter(opt.k as FilterStatus)}
            className={[
              "rounded-[4px] px-3 py-1.5 text-sm transition-colors",
              filter === opt.k
                ? "bg-[color:var(--ink-3)] text-[color:var(--paper)]"
                : "text-[color:var(--mute-2)] hover:bg-[color:var(--ink-2)]",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Не удалось получить расписание: {error}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-[color:var(--text-muted)]">
          Загружаю…
        </div>
      ) : posts.length === 0 ? (
        <div className="surface-card p-10 text-center">
          <div className="display-serif mb-3 text-2xl">
            Пока нет запланированных публикаций
          </div>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Создавай пост из карточки готового рилса — появится здесь.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {posts.map((p) => (
            <li key={p.id} className="surface-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="stamp">
                      {PLATFORM_LABELS[p.platform] ?? p.platform}
                    </span>
                    <span
                      className={`stamp ${statusStampClass(p.status)}`}
                    >
                      {STATUS_LABELS[p.status] ?? p.status}
                    </span>
                    <span className="mono text-[12px] text-[color:var(--text-muted)]">
                      {p.reel_id}
                    </span>
                  </div>
                  <div className="display-serif text-xl">
                    {p.title || "(без заголовка)"}
                  </div>
                  <div className="text-sm text-[color:var(--text-secondary)]">
                    Публикация:{" "}
                    {new Date(p.publish_at).toLocaleString("ru-RU")}
                    {" · "}видимость: {p.visibility}
                    {p.notify_subscribers ? " · с уведомлением подписчикам" : ""}
                  </div>
                  {p.external_url ? (
                    <a
                      href={p.external_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm underline underline-offset-2 hover:text-[color:var(--text-primary)]"
                    >
                      {p.external_url}
                    </a>
                  ) : null}
                  {p.error_message ? (
                    <div className="rounded border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-2 text-[12px] text-[color:var(--danger)]">
                      Попытка {p.attempts}/3: {p.error_message}
                    </div>
                  ) : null}
                </div>
                {p.status === "pending" || p.status === "error" ? (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleCancel(p.id)}
                  >
                    Отменить
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function countByStatus(posts: ScheduledPost[]): Record<string, number> {
  const counts: Record<string, number> = {
    pending: 0,
    uploading: 0,
    done: 0,
    error: 0,
    cancelled: 0,
  };
  for (const p of posts) {
    if (counts[p.status] !== undefined) counts[p.status] += 1;
  }
  return counts;
}

function statusStampClass(status: string): string {
  if (status === "done") return "ok";
  if (status === "error") return "hot";
  return "";
}
