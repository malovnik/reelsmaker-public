
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

type Platform = "youtube" | "instagram";
type Visibility = "public" | "unlisted" | "private";

interface Props {
  jobId: string;
  reelId: string;
  defaultTitle?: string;
}

const PLATFORM_LABELS: Record<Platform, string> = {
  youtube: "YouTube Shorts",
  instagram: "Instagram Reels",
};

function defaultPublishAt(): { date: string; time: string } {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  return { date, time };
}

export function ScheduleButton({ jobId, reelId, defaultTitle }: Props) {
  const [open, setOpen] = useState(false);
  const [platform, setPlatform] = useState<Platform>("youtube");
  const [title, setTitle] = useState(defaultTitle ?? "");
  const [description, setDescription] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [notifySubscribers, setNotifySubscribers] = useState(false);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const defaults = defaultPublishAt();
    setDate((prev) => prev || defaults.date);
    setTime((prev) => prev || defaults.time);
    setTitle((prev) => prev || defaultTitle || `Рилс ${reelId}`);
  }, [open, defaultTitle, reelId]);

  async function submit() {
    if (!date || !time || !title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const isoLocal = new Date(`${date}T${time}:00`).toISOString();
      const tags = tagsRaw
        .split(/[,\n]/)
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, 15);
      const response = await fetch(`/api/v1/schedule`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          job_id: jobId,
          reel_id: reelId,
          platform,
          title: title.trim(),
          description,
          tags,
          visibility,
          publish_at: isoLocal,
          notify_subscribers: notifySubscribers,
        }),
      });
      if (!response.ok) {
        let detail: unknown = null;
        try {
          detail = await response.json();
        } catch {
          detail = await response.text();
        }
        throw new ApiError(response.status, detail);
      }
      setDone(true);
      setTimeout(() => {
        setOpen(false);
        setDone(false);
      }, 1200);
    } catch (exc) {
      const message =
        exc instanceof ApiError && exc.detail
          ? extractDetail(exc.detail)
          : (exc as Error).message;
      setError(message ?? "Не удалось запланировать публикацию");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2.5 py-1 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--accent-primary)] hover:text-[color:var(--accent-primary)]"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
        Запланировать
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="surface-card w-full max-w-md overflow-hidden">
            <div className="border-b border-[color:var(--border-default)] p-5">
              <h3 className="display-serif text-xl text-[color:var(--text-primary)]">
                Запланировать публикацию
              </h3>
              <p className="mt-1 text-[12px] text-[color:var(--text-muted)]">
                Рилс {reelId}
              </p>
            </div>

            <div className="flex flex-col gap-4 p-5">
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                  Платформа
                </label>
                <div className="flex gap-2">
                  {(Object.keys(PLATFORM_LABELS) as Platform[]).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setPlatform(p)}
                      className={`flex-1 rounded-[4px] border px-3 py-2 text-sm font-medium transition-colors ${
                        platform === p
                          ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary)] text-[color:var(--accent-on-primary)]"
                          : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--text-primary)]"
                      }`}
                    >
                      {PLATFORM_LABELS[p]}
                    </button>
                  ))}
                </div>
              </div>

              {platform === "instagram" && (
                <div className="rounded-md border border-[color:var(--warning)]/40 bg-[color:var(--warning)]/10 p-3 text-[11px] leading-snug text-[color:var(--warning)]">
                  <span className="block font-medium">
                    Требуется одобрение Facebook App Review
                  </span>
                  <span className="text-[color:var(--warning)]">
                    Instagram Graph API публикует рилсы только из аккаунтов,
                    чей Business-профиль привязан к Facebook App с permissions
                    <span className="mono"> instagram_content_publish</span>.
                    Без approval backend вернёт ошибку 400 от Graph API.
                  </span>
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                  Заголовок
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={500}
                  className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                  placeholder="Заголовок для YouTube / подпись Instagram"
                />
              </div>

              <div className="flex gap-3">
                <div className="flex flex-1 flex-col gap-1.5">
                  <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                    Дата
                  </label>
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                  />
                </div>
                <div className="flex flex-1 flex-col gap-1.5">
                  <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                    Время
                  </label>
                  <input
                    type="time"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                    className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                  Описание
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  maxLength={5000}
                  placeholder="Подпись / описание под роликом"
                  className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                  Теги (через запятую, максимум 15)
                </label>
                <input
                  type="text"
                  value={tagsRaw}
                  onChange={(e) => setTagsRaw(e.target.value)}
                  placeholder="shorts, reels, контент"
                  className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                />
              </div>

              <div className="flex gap-3">
                <div className="flex flex-1 flex-col gap-1.5">
                  <label className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-muted)]">
                    Видимость
                  </label>
                  <select
                    value={visibility}
                    onChange={(e) => setVisibility(e.target.value as Visibility)}
                    className="rounded-[4px] border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                  >
                    <option value="private">Приватно</option>
                    <option value="unlisted">По ссылке</option>
                    <option value="public">Публично</option>
                  </select>
                </div>
                {platform === "youtube" && (
                  <label className="flex flex-1 items-end gap-2 text-[12px] text-[color:var(--text-secondary)]">
                    <input
                      type="checkbox"
                      checked={notifySubscribers}
                      onChange={(e) => setNotifySubscribers(e.target.checked)}
                      className="size-4"
                    />
                    Уведомить подписчиков
                  </label>
                )}
              </div>

              {error && (
                <div className="rounded-md border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-2 text-[12px] text-[color:var(--danger)]">
                  {error}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] px-5 py-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-[4px] px-3 py-1.5 text-sm text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
              >
                Отмена
              </button>
              <button
                type="button"
                disabled={saving || done || !date || !time || !title.trim()}
                onClick={submit}
                className="rounded-[4px] bg-[color:var(--accent-primary)] px-4 py-1.5 text-sm font-medium text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {done ? "Запланировано" : saving ? "Сохраняю…" : "Запланировать"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function extractDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    "detail" in detail &&
    typeof (detail as { detail: unknown }).detail === "string"
  ) {
    return (detail as { detail: string }).detail;
  }
  return null;
}
