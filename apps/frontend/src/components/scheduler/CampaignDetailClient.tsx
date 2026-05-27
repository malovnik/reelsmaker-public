
import { Link } from "react-router-dom";
import { useRouter } from "@/lib/router-compat";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  schedulerApi,
  type AssignmentStatus,
  type CampaignDetail,
  type PublerNetwork,
  type ScheduleAssignment,
  type ScheduleCampaign,
} from "@/lib/api/scheduler";

interface Props {
  initialCampaign: CampaignDetail;
}

const DISPLAY_TZ = "Asia/Ho_Chi_Minh";

const STATUS_ORDER: AssignmentStatus[] = [
  "draft",
  "queued",
  "uploading",
  "scheduling",
  "scheduled",
  "published",
  "failed",
  "cancelled",
];

function assignmentStatusBadge(status: AssignmentStatus): {
  label: string;
  color: string;
} {
  switch (status) {
    case "draft":
      return { label: "черновик", color: "var(--mute-2)" };
    case "queued":
      return { label: "в очереди", color: "var(--mute-2)" };
    case "uploading":
      return { label: "загрузка", color: "var(--gold)" };
    case "scheduling":
      return { label: "планируется", color: "var(--gold)" };
    case "scheduled":
      return { label: "запланирован", color: "var(--gold)" };
    case "published":
      return { label: "опубликован", color: "var(--gold)" };
    case "failed":
      return { label: "ошибка", color: "var(--danger)" };
    case "cancelled":
      return { label: "отменён", color: "var(--danger)" };
    default:
      return { label: status, color: "var(--mute-2)" };
  }
}

function campaignStatusBadge(status: ScheduleCampaign["status"]): {
  label: string;
  color: string;
} {
  switch (status) {
    case "draft":
      return { label: "черновик", color: "var(--mute-2)" };
    case "approved":
      return { label: "в работе", color: "var(--gold)" };
    case "cancelled":
      return { label: "отменена", color: "var(--danger)" };
    default:
      return { label: status, color: "var(--mute-2)" };
  }
}

function networkLabel(network: PublerNetwork): string {
  return network === "instagram" ? "IG" : "YT";
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatScheduledDisplay(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    return d.toLocaleString("ru-RU", {
      timeZone: DISPLAY_TZ,
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return utcIso;
  }
}

/**
 * Convert UTC ISO string to a value suitable for `<input type="datetime-local">`
 * interpreted in `Asia/Ho_Chi_Minh`.
 *
 * Output shape: `YYYY-MM-DDTHH:mm` (matches datetime-local).
 */
function utcIsoToLocalInput(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: DISPLAY_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const pick = (t: string) =>
      parts.find((p) => p.type === t)?.value ?? "00";
    return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}`;
  } catch {
    return "";
  }
}

/**
 * Parse `datetime-local` string (naive, no tz) as wallclock time in
 * `Asia/Ho_Chi_Minh` and return a UTC ISO string.
 */
function localInputToUtcIso(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local);
  if (!m) return null;
  const [, yStr, moStr, dStr, hStr, miStr] = m;
  const y = Number(yStr);
  const mo = Number(moStr);
  const d = Number(dStr);
  const h = Number(hStr);
  const mi = Number(miStr);
  const asIfUtc = Date.UTC(y, mo - 1, d, h, mi, 0);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: DISPLAY_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date(asIfUtc));
  const pick = (t: string) =>
    Number(parts.find((p) => p.type === t)?.value ?? "0");
  const displayed = Date.UTC(
    pick("year"),
    pick("month") - 1,
    pick("day"),
    pick("hour"),
    pick("minute"),
    pick("second"),
  );
  const offsetMs = displayed - asIfUtc;
  return new Date(asIfUtc - offsetMs).toISOString();
}

function CaptionPreview({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const isLong = text.length > 120;
  const shown = !isLong || open ? text : `${text.slice(0, 120)}…`;
  return (
    <div className="flex flex-col gap-1">
      <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-[color:var(--paper-dim)]">
        {shown || "—"}
      </p>
      {isLong ? (
        <button
          type="button"
          onClick={() => setOpen((p) => !p)}
          className="mono self-start text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
        >
          {open ? "свернуть" : "показать"}
        </button>
      ) : null}
    </div>
  );
}

function ErrorMessageBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const isLong = text.length > 80;
  return (
    <div className="mt-1 flex max-w-[260px] flex-col gap-1">
      <div
        className={
          open || !isLong
            ? "whitespace-pre-wrap break-words font-mono text-[10px] leading-snug text-[color:var(--danger)]"
            : "truncate font-mono text-[10px] text-[color:var(--danger)]"
        }
        title={isLong ? text : undefined}
      >
        {open || !isLong ? text : `${text.slice(0, 80)}…`}
      </div>
      {isLong ? (
        <button
          type="button"
          onClick={() => setOpen((p) => !p)}
          className="mono self-start text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
        >
          {open ? "свернуть" : "развернуть"}
        </button>
      ) : null}
    </div>
  );
}

interface EditModalProps {
  open: boolean;
  assignment: ScheduleAssignment | null;
  onClose: () => void;
  onSaved: (updated: ScheduleAssignment) => void;
}

function AssignmentEditModal({
  open,
  assignment,
  onClose,
  onSaved,
}: EditModalProps) {
  const [caption, setCaption] = useState("");
  const [title, setTitle] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");
  const [scheduledLocal, setScheduledLocal] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !assignment) return;
    setCaption(assignment.caption ?? "");
    setTitle(assignment.title ?? "");
    setHashtagsText((assignment.hashtags ?? []).join(" "));
    setScheduledLocal(utcIsoToLocalInput(assignment.scheduled_at_utc));
    setError(null);
    setSaving(false);
  }, [open, assignment]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open || !assignment) return null;

  const isYoutube = assignment.network === "youtube";

  const handleSave = async () => {
    setError(null);
    const hashtags = hashtagsText
      .split(/[\s,]+/)
      .map((t) => t.replace(/^#+/, "").trim())
      .filter((t) => t.length > 0);
    let scheduledUtc: string | undefined;
    if (scheduledLocal) {
      const parsed = localInputToUtcIso(scheduledLocal);
      if (!parsed) {
        setError("Некорректная дата/время");
        return;
      }
      scheduledUtc = parsed;
    }
    setSaving(true);
    try {
      const updated = await schedulerApi.updateAssignment(assignment.id, {
        caption: caption,
        title: isYoutube ? title : undefined,
        hashtags,
        scheduled_at_utc: scheduledUtc,
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="assignment-edit-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="surface-card w-full max-w-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2
            id="assignment-edit-title"
            className="display-serif text-[22px] leading-tight text-[color:var(--paper)]"
          >
            Редактировать публикацию
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
          >
            ×
          </button>
        </div>

        <div className="mono mt-2 text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          id · {assignment.id} · {networkLabel(assignment.network)} ·{" "}
          {assignment.publer_account_id}
        </div>

        <div className="divider my-4">поля</div>

        <div className="flex flex-col gap-4">
          {isYoutube ? (
            <label className="flex flex-col gap-1.5">
              <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Title (YouTube)
              </span>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={100}
                placeholder="Заголовок для YouTube Shorts"
                className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
              />
            </label>
          ) : null}

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Caption
            </span>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={6}
              placeholder="Текст публикации"
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Хэштеги (через пробел или запятую, без #)
            </span>
            <input
              type="text"
              value={hashtagsText}
              onChange={(e) => setHashtagsText(e.target.value)}
              placeholder="reels vibes viral"
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Время публикации ({DISPLAY_TZ})
            </span>
            <input
              type="datetime-local"
              value={scheduledLocal}
              onChange={(e) => setScheduledLocal(e.target.value)}
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
          </label>
        </div>

        {error ? (
          <p className="mt-3 text-[11px] text-[color:var(--danger)]">{error}</p>
        ) : null}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function CampaignDetailClient({ initialCampaign }: Props) {
  const router = useRouter();
  const [campaign, setCampaign] = useState<CampaignDetail>(initialCampaign);
  const [refreshing, setRefreshing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<ScheduleAssignment | null>(null);

  const hasActive = useMemo(
    () =>
      campaign.assignments.some((a) =>
        a.status === "draft" ||
        a.status === "queued" ||
        a.status === "uploading" ||
        a.status === "scheduling",
      ),
    [campaign.assignments],
  );

  useEffect(() => {
    if (!hasActive) return;
    if (editing !== null) return;
    let cancelled = false;
    const tick = async () => {
      // Не дёргаем сервер пока вкладка скрыта — кампания может быть
      // открыта часами в фоне, 3-секундный poll уносит трафик впустую.
      if (document.visibilityState !== "visible") return;
      try {
        const next = await schedulerApi.getCampaign(campaign.id);
        if (!cancelled) setCampaign(next);
      } catch {
        // polling умолчит ошибки — пользователь увидит stale данные,
        // но ручной «Обновить» покажет error в баннере
      }
    };
    const id = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [campaign.id, hasActive, editing]);

  const breakdown = useMemo(() => {
    const counts: Record<AssignmentStatus, number> = {
      draft: 0,
      queued: 0,
      uploading: 0,
      scheduling: 0,
      scheduled: 0,
      published: 0,
      failed: 0,
      cancelled: 0,
    };
    for (const a of campaign.assignments) counts[a.status] += 1;
    return counts;
  }, [campaign.assignments]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const next = await schedulerApi.getCampaign(campaign.id);
      setCampaign(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }, [campaign.id]);

  const handleApproveCampaign = useCallback(async () => {
    if (
      !confirm(
        `Одобрить кампанию «${campaign.name}»? Все черновики перейдут в очередь и worker начнёт доставку в Publer.`,
      )
    ) {
      return;
    }
    setApproving(true);
    setError(null);
    try {
      await schedulerApi.approveCampaign(campaign.id);
      const next = await schedulerApi.getCampaign(campaign.id);
      setCampaign(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setApproving(false);
    }
  }, [campaign.id, campaign.name]);

  const handleDeleteCampaign = useCallback(async () => {
    if (
      !confirm(
        `Удалить кампанию «${campaign.name}»? Все назначения внутри будут удалены.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await schedulerApi.deleteCampaign(campaign.id);
      router.push("/scheduler");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  }, [campaign.id, campaign.name, router]);

  const handleCancel = useCallback(
    async (a: ScheduleAssignment) => {
      if (!confirm(`Отменить публикацию id·${a.id}?`)) return;
      setCancellingId(a.id);
      setError(null);
      try {
        const updated = await schedulerApi.cancelAssignment(a.id);
        setCampaign((prev) => ({
          ...prev,
          assignments: prev.assignments.map((x) =>
            x.id === updated.id ? updated : x,
          ),
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setCancellingId(null);
      }
    },
    [],
  );

  const handleRetry = useCallback(
    async (a: ScheduleAssignment) => {
      setRetryingId(a.id);
      setError(null);
      try {
        const updated = await schedulerApi.retryAssignment(a.id);
        setCampaign((prev) => ({
          ...prev,
          assignments: prev.assignments.map((x) =>
            x.id === updated.id ? updated : x,
          ),
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRetryingId(null);
      }
    },
    [],
  );

  const handleSaved = useCallback((updated: ScheduleAssignment) => {
    setCampaign((prev) => ({
      ...prev,
      assignments: prev.assignments.map((x) =>
        x.id === updated.id ? updated : x,
      ),
    }));
    setEditing(null);
  }, []);

  const badge = campaignStatusBadge(campaign.status);
  const datesSorted = [...campaign.dates].sort();
  const firstDate = datesSorted[0];
  const lastDate = datesSorted[datesSorted.length - 1];

  return (
    <div className="flex flex-col gap-6">
      <nav className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
        <Link
          to="/scheduler"
          className="transition-colors hover:text-[color:var(--paper)]"
        >
          ← шедулер
        </Link>
      </nav>

      <header className="surface-card flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="display-serif text-3xl leading-tight tracking-tight text-[color:var(--paper)]">
              {campaign.name}
            </div>
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              id · {campaign.id} · tz · {campaign.tz} · время ·{" "}
              {campaign.time_of_day}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="mono shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
              style={{ color: badge.color, borderColor: badge.color }}
            >
              {badge.label}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {refreshing ? "Обновляю…" : "Обновить"}
            </button>
            {campaign.status === "draft" && (
              <button
                type="button"
                onClick={handleApproveCampaign}
                disabled={approving}
                className="rounded-md border border-[color:var(--gold)] px-3 py-1.5 text-[12px] text-[color:var(--gold)] transition-colors hover:bg-[color:var(--gold)] hover:text-[color:var(--ink)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {approving ? "Одобряю…" : "Одобрить"}
              </button>
            )}
            <button
              type="button"
              onClick={handleDeleteCampaign}
              disabled={deleting}
              className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleting ? "Удаляю…" : "Удалить кампанию"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              даты · {campaign.dates.length}
            </div>
            <div className="text-sm text-[color:var(--text-secondary)]">
              {firstDate ? (
                <>
                  {formatDate(firstDate)}
                  {lastDate && lastDate !== firstDate
                    ? ` — ${formatDate(lastDate)}`
                    : ""}
                </>
              ) : (
                "—"
              )}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              публикации
            </div>
            <div className="text-sm text-[color:var(--text-secondary)]">
              {campaign.assignments.length}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              создана
            </div>
            <div className="text-sm text-[color:var(--text-secondary)]">
              {formatDate(campaign.created_at)}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {STATUS_ORDER.map((s) => {
            const count = breakdown[s];
            if (count === 0) return null;
            const b = assignmentStatusBadge(s);
            return (
              <span
                key={s}
                className="mono rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                style={{ color: b.color, borderColor: b.color }}
              >
                {b.label} · {count}
              </span>
            );
          })}
        </div>
      </header>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      <section className="flex flex-col gap-3">
        <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          публикации · {campaign.assignments.length}
        </div>

        {campaign.assignments.length === 0 ? (
          <div className="surface-card flex flex-col items-center justify-center gap-2 p-8 text-center">
            <div className="display-serif text-xl text-[color:var(--paper)]">
              Нет публикаций
            </div>
            <p className="text-sm text-[color:var(--text-secondary)]">
              В кампании пока нет назначений.
            </p>
          </div>
        ) : (
          <div className="surface-card overflow-x-auto p-0">
            <table className="w-full min-w-[960px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[color:var(--line)]">
                  <th className="mono px-4 py-3 text-[10px] font-normal uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    сеть · аккаунт
                  </th>
                  <th className="mono px-4 py-3 text-[10px] font-normal uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    время ({DISPLAY_TZ.split("/")[1]?.replace("_", " ")})
                  </th>
                  <th className="mono px-4 py-3 text-[10px] font-normal uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    статус
                  </th>
                  <th className="mono px-4 py-3 text-[10px] font-normal uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    контент
                  </th>
                  <th className="mono px-4 py-3 text-[10px] font-normal uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {campaign.assignments.map((a) => {
                  const sb = assignmentStatusBadge(a.status);
                  const cancellable =
                    a.status !== "published" &&
                    a.status !== "cancelled" &&
                    a.status !== "failed";
                  const retryable =
                    a.status === "failed" || a.status === "cancelled";
                  const editable =
                    a.status === "draft" ||
                    a.status === "queued" ||
                    a.status === "scheduled";
                  return (
                    <tr
                      key={a.id}
                      className="border-b border-[color:var(--line)] last:border-b-0 align-top"
                    >
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <span
                            className="mono inline-flex w-fit rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                            style={{
                              color: "var(--gold)",
                              borderColor: "var(--gold)",
                            }}
                          >
                            {networkLabel(a.network)}
                          </span>
                          <span
                            className="mono truncate text-[11px] text-[color:var(--paper-dim)]"
                            title={a.publer_account_id}
                          >
                            {a.publer_account_id.slice(0, 10)}
                            {a.publer_account_id.length > 10 ? "…" : ""}
                          </span>
                          <span className="mono text-[10px] text-[color:var(--mute-2)]">
                            id · {a.id}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="mono text-[12px] text-[color:var(--paper)]">
                          {formatScheduledDisplay(a.scheduled_at_utc)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className="mono inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                          style={{ color: sb.color, borderColor: sb.color }}
                        >
                          {sb.label}
                        </span>
                        {a.error_message ? (
                          <ErrorMessageBlock text={a.error_message} />
                        ) : null}
                      </td>
                      <td className="max-w-[360px] px-4 py-3">
                        <div className="flex flex-col gap-2">
                          {a.network === "youtube" && a.title ? (
                            <div className="text-[12px] font-medium text-[color:var(--paper)]">
                              {a.title}
                            </div>
                          ) : null}
                          <CaptionPreview text={a.caption} />
                          {a.hashtags && a.hashtags.length > 0 ? (
                            <div className="mono text-[11px] text-[color:var(--gold)]">
                              {a.hashtags
                                .map((h) => `#${h.replace(/^#+/, "")}`)
                                .join(" ")}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1.5">
                          <button
                            type="button"
                            onClick={() => setEditing(a)}
                            disabled={!editable}
                            className="rounded-md border border-[color:var(--line)] px-2.5 py-1 text-[11px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Редактировать
                          </button>
                          <button
                            type="button"
                            onClick={() => handleCancel(a)}
                            disabled={!cancellable || cancellingId === a.id}
                            className="rounded-md border border-[color:var(--line)] px-2.5 py-1 text-[11px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)] disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {cancellingId === a.id ? "Отменяю…" : "Отменить"}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRetry(a)}
                            disabled={!retryable || retryingId === a.id}
                            className="rounded-md border border-[color:var(--line)] px-2.5 py-1 text-[11px] text-[color:var(--gold)] transition-colors hover:border-[color:var(--gold)] disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {retryingId === a.id ? "Ставлю…" : "Повторить"}
                          </button>
                          {a.publer_post_url ? (
                            <a
                              href={a.publer_post_url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="rounded-md border border-[color:var(--line)] px-2.5 py-1 text-center text-[11px] text-[color:var(--gold)] transition-colors hover:opacity-90"
                            >
                              Открыть пост ↗
                            </a>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <AssignmentEditModal
        open={editing !== null}
        assignment={editing}
        onClose={() => setEditing(null)}
        onSaved={handleSaved}
      />
    </div>
  );
}
