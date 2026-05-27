
import { Link } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { api, type ArtifactRead, type JobRead, type VisionProfile } from "@/lib/api";
import { PROFILE_LABELS } from "@/components/ProfileSelector";

const PROFILE_COLOR: Record<VisionProfile, string> = {
  talking_head: "var(--profile-talking-head)",
  fashion: "var(--profile-fashion)",
  travel: "var(--profile-travel)",
  screencast: "var(--profile-screencast)",
  custom: "var(--profile-custom)",
};

const STATUS_META: Record<
  string,
  { label: string; bg: string; text: string; dot: string }
> = {
  pending: {
    label: "в очереди",
    bg: "bg-[color:var(--surface-sunken)]",
    text: "text-[color:var(--text-muted)]",
    dot: "bg-[color:var(--text-muted)]",
  },
  running: {
    label: "обрабатывается",
    bg: "bg-[color:var(--warning)]/10",
    text: "text-[color:var(--warning)]",
    dot: "bg-[color:var(--warning)] animate-pulse",
  },
  done: {
    label: "готово",
    bg: "bg-[color:var(--success)]/10",
    text: "text-[color:var(--success)]",
    dot: "bg-[color:var(--success)]",
  },
  error: {
    label: "ошибка",
    bg: "bg-[color:var(--danger)]/10",
    text: "text-[color:var(--danger)]",
    dot: "bg-[color:var(--danger)]",
  },
  cancelled: {
    label: "отменено",
    bg: "bg-[color:var(--surface-sunken)]",
    text: "text-[color:var(--text-muted)]",
    dot: "bg-[color:var(--text-muted)]",
  },
};

interface Props {
  job: JobRead;
  isSelected?: boolean;
  onToggleSelect?: () => void;
  onRename?: (jobId: string, newName: string | null) => void;
  compact?: boolean;
}

export function JobCard({
  job,
  isSelected = false,
  onToggleSelect,
  onRename,
  compact = false,
}: Props) {
  const meta = STATUS_META[job.status] ?? STATUS_META.pending;
  const isActive = job.status === "running" || job.status === "pending";
  const profileColor = PROFILE_COLOR[job.vision_profile] ?? PROFILE_COLOR.custom;
  const profileLabel =
    PROFILE_LABELS[job.vision_profile] ?? job.vision_profile;
  const [thumbFailed, setThumbFailed] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewFetchedRef = useRef(false);
  const isDone = job.status === "done";

  useEffect(() => {
    if (!isHovering || !isDone || previewFetchedRef.current || compact) return;
    previewFetchedRef.current = true;
    let cancelled = false;
    (async () => {
      try {
        const artifacts = await api.listArtifacts(job.id);
        if (cancelled) return;
        const reel = artifacts.find(
          (a: ArtifactRead) =>
            a.kind === "reel_output" && a.path.toLowerCase().endsWith(".mp4"),
        );
        if (reel) {
          setPreviewUrl(buildReelFileUrl(job.id, reel.path));
        }
      } catch {
        // graceful degrade — остаёмся на thumbnail
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isHovering, isDone, compact, job.id]);

  if (compact) {
    return (
      <Link
        to={`/jobs/${job.id}`}
        className={`surface-card group flex items-center gap-3 px-3 py-2 transition-colors hover:bg-[color:var(--surface-raised)] ${
          isSelected ? "ring-2 ring-[color:var(--accent-primary)]" : ""
        }`}
      >
        {onToggleSelect && (
          <SelectCheckbox
            selected={isSelected}
            onToggle={onToggleSelect}
          />
        )}
        <div className="relative h-12 w-20 shrink-0 overflow-hidden rounded-[4px] bg-[color:var(--surface-sunken)]">
          {thumbFailed ? null : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`/api/v1/jobs/${job.id}/thumbnail`}
              alt=""
              loading="lazy"
              onError={() => setThumbFailed(true)}
              className="size-full object-cover"
            />
          )}
        </div>
        <span
          className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
          style={{
            background: `${profileColor}22`,
            color: profileColor,
            border: `1px solid ${profileColor}44`,
          }}
        >
          {profileLabel}
        </span>
        <div className="flex-1 min-w-0">
          <RenameableTitle job={job} onRename={onRename} />
        </div>
        <span
          className={`hidden shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold sm:inline-flex ${meta.bg} ${meta.text}`}
        >
          <span className={`size-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
        <span className="hidden shrink-0 font-mono text-[11px] text-[color:var(--text-muted)] md:inline">
          {formatSize(job.source_size_bytes)}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-[color:var(--text-muted)]">
          {formatRelative(job.created_at)}
        </span>
      </Link>
    );
  }

  return (
    <Link
      to={`/jobs/${job.id}`}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
      className={`surface-card group relative flex flex-col overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)] ${
        isSelected
          ? "ring-2 ring-[color:var(--accent-primary)] ring-offset-2 ring-offset-[color:var(--surface-canvas)]"
          : ""
      }`}
    >
      <div className="relative aspect-video overflow-hidden bg-[color:var(--surface-sunken)]">
        {isHovering && previewUrl ? (
          <video
            src={previewUrl}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            className="size-full object-cover"
          />
        ) : thumbFailed ? (
          <div className="flex size-full items-center justify-center">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.4}
              className="text-[color:var(--text-muted)]"
              aria-hidden="true"
            >
              <path d="M15 10l4.553-2.276A1 1 0 0 1 21 8.618v6.764a1 1 0 0 1-1.447.894L15 14" />
              <rect x="3" y="6" width="12" height="12" rx="2" />
            </svg>
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={api.jobThumbnailUrl(job.id)}
            alt=""
            loading="lazy"
            className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            onError={() => setThumbFailed(true)}
          />
        )}

        <span
          className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium backdrop-blur-md"
          style={{
            color: profileColor,
            borderColor: profileColor,
            backgroundColor: "rgba(20, 16, 12, 0.78)",
          }}
        >
          <span
            aria-hidden="true"
            className="size-1.5 rounded-full"
            style={{ backgroundColor: profileColor }}
          />
          {profileLabel}
        </span>

        {onToggleSelect && (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onToggleSelect();
            }}
            aria-pressed={isSelected}
            aria-label={isSelected ? "Снять выбор" : "Выбрать нарезку"}
            className={`absolute right-3 top-3 flex size-8 items-center justify-center rounded-full border backdrop-blur transition-opacity ${
              isSelected
                ? "border-white/40 bg-[color:var(--accent-primary)] text-white opacity-100"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] text-[color:var(--text-secondary)] opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
            }`}
          >
            {isSelected ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={3}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <span
                aria-hidden="true"
                className="size-3 rounded-full border-2 border-current"
              />
            )}
          </button>
        )}

        {isActive && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-[color:var(--surface-sunken)]">
            <div
              className="h-full gradient-accent transition-[width] duration-500"
              style={{ width: `${job.progress}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <RenameableTitle
            job={job}
            onRename={onRename}
          />
          <span
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.bg} ${meta.text}`}
          >
            <span className={`size-1.5 rounded-full ${meta.dot}`} />
            {meta.label}
          </span>
        </div>

        <div className="mt-auto flex items-center justify-between text-[11px] text-[color:var(--text-muted)]">
          <span className="font-mono">{formatSize(job.source_size_bytes)}</span>
          <span className="font-mono">{formatRelative(job.created_at)}</span>
        </div>
      </div>
    </Link>
  );
}

function SelectCheckbox({
  selected,
  onToggle,
}: {
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={selected ? "Снять выбор" : "Выбрать пакет"}
      aria-pressed={selected}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className={`flex size-5 shrink-0 items-center justify-center rounded-[3px] border transition-colors ${
        selected
          ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary)]"
          : "border-[color:var(--border-default)] hover:border-[color:var(--text-primary)]"
      }`}
    >
      {selected && (
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--accent-on-primary)"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </button>
  );
}

function RenameableTitle({
  job,
  onRename,
}: {
  job: JobRead;
  onRename?: (jobId: string, newName: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(job.display_name ?? job.source_filename);
  const displayed = job.display_name ?? job.source_filename;

  function commit() {
    const trimmed = draft.trim();
    const next = trimmed.length === 0 ? null : trimmed;
    if (next === (job.display_name ?? null)) {
      setEditing(false);
      return;
    }
    onRename?.(job.id, next);
    setEditing(false);
  }

  function startEdit(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDraft(displayed);
    setEditing(true);
  }

  if (editing && onRename) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
          if (e.key === "Escape") {
            setDraft(displayed);
            setEditing(false);
          }
        }}
        className="w-full rounded-[4px] border border-[color:var(--accent-primary)] bg-[color:var(--surface-canvas)] px-2 py-1 text-sm text-[color:var(--text-primary)] outline-none"
        maxLength={256}
      />
    );
  }

  return (
    <div className="group/title flex items-center gap-2 min-w-0">
      <h3
        className="line-clamp-2 break-all text-sm font-medium text-[color:var(--text-primary)]"
        onDoubleClick={onRename ? startEdit : undefined}
      >
        {displayed}
      </h3>
      {onRename && (
        <button
          type="button"
          aria-label="Переименовать"
          onClick={startEdit}
          className="shrink-0 rounded-[3px] p-1 text-[color:var(--text-muted)] opacity-0 transition-opacity hover:bg-[color:var(--surface-raised)] hover:text-[color:var(--text-primary)] group-hover/title:opacity-100 focus:opacity-100"
          title="Переименовать (или двойной клик)"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
          </svg>
        </button>
      )}
    </div>
  );
}

function buildReelFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2) {
    return `/api/v1/files/${jobId}/reels/${encodeURIComponent(relativePath)}`;
  }
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} ГБ`;
}

function formatRelative(iso: string): string {
  const date = new Date(iso);
  const diff = Math.round((Date.now() - date.getTime()) / 60000);
  if (diff < 1) return "только что";
  if (diff < 60) return `${diff} мин назад`;
  const h = Math.round(diff / 60);
  if (h < 24) return `${h} ч назад`;
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}
