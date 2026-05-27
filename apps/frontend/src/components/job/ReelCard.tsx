
import { Link } from "react-router-dom";
import { useState, useTransition } from "react";
import { api, type ArtifactRead } from "@/lib/api";
import {
  computeViralScore,
  viralInputFromMeta,
  type ViralScoreBreakdown,
} from "@/lib/viralScore";
import { ScheduleButton } from "@/components/job/ScheduleButton";

export type LikeState = "none" | "like" | "dislike";

interface Props {
  jobId: string;
  artifact: ArtifactRead;
  onUpdate?: (updated: ArtifactRead) => void;
  isSelected?: boolean;
  onToggleSelect?: () => void;
  onDelete?: () => void;
  busy?: boolean;
}

export function ReelCard({
  jobId,
  artifact,
  onUpdate,
  isSelected = false,
  onToggleSelect,
  onDelete,
  busy = false,
}: Props) {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const meta = artifact.meta as Record<string, unknown>;
  const reelId = String(meta.reel_id ?? artifact.id);
  const duration =
    typeof meta.duration_sec === "number" ? meta.duration_sec : undefined;
  const breakdown = computeViralScore(viralInputFromMeta(meta));
  // T9 — cross-context risk. >0.6 показываем amber badge: рилс собран
  // из временно разнесённых сегментов, перед публикацией нужно убедиться
  // что смысл сохранился.
  const crossContextRisk =
    typeof meta.cross_context_risk === "number"
      ? meta.cross_context_risk
      : null;
  const showCrossContextWarning =
    crossContextRisk !== null && crossContextRisk > 0.6;
  const url = buildFileUrl(jobId, artifact.path);
  const initialLike = toLikeState(meta.liked);
  const [liked, setLiked] = useState<LikeState>(initialLike);
  const [isPending, startTransition] = useTransition();
  const disabled = isPending || busy;

  function pushLike(next: LikeState) {
    const previous = liked;
    setLiked(next);
    startTransition(async () => {
      try {
        const updated = await api.updateArtifactLike(jobId, artifact.id, next);
        if (onUpdate) onUpdate(updated);
      } catch {
        setLiked(previous);
      }
    });
  }

  return (
    <article
      className={`surface-card group flex flex-col overflow-hidden transition-shadow duration-200 hover:shadow-[var(--shadow-md)] ${
        isSelected
          ? "ring-2 ring-[color:var(--accent-primary)] ring-offset-2 ring-offset-[color:var(--surface-canvas)]"
          : ""
      }`}
    >
      <div className="relative aspect-[9/16] bg-black">
        <video
          src={url}
          controls
          playsInline
          preload="metadata"
          className="size-full object-contain"
        />
        <ScoreBadge
          breakdown={breakdown}
          onToggle={() => setShowBreakdown((v) => !v)}
          showBreakdown={showBreakdown}
        />
        {onToggleSelect && (
          <SelectCheckbox
            selected={isSelected}
            onToggle={onToggleSelect}
            disabled={disabled}
          />
        )}
        <LikeOverlay liked={liked} onChange={pushLike} disabled={disabled} />
        {onDelete && (
          <DeleteButton onDelete={onDelete} disabled={disabled} reelId={reelId} />
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-mono text-[color:var(--text-secondary)]">
            {reelId}
          </span>
          {duration !== undefined && (
            <span className="text-[color:var(--text-muted)]">
              {duration.toFixed(1)} с
            </span>
          )}
        </div>

        <p className="text-[11px] leading-snug text-[color:var(--text-muted)]">
          {breakdown.comment}
        </p>

        {showCrossContextWarning && (
          <CrossContextBadge risk={crossContextRisk ?? 0} />
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <a
            href={url}
            download
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--accent-primary)] transition-colors hover:text-[color:var(--accent-primary-hover)]"
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
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Скачать
          </a>
          <div className="flex items-center gap-2">
            <ScheduleButton jobId={jobId} reelId={reelId} />
            <Link
              to={`/jobs/${jobId}/reels/${artifact.id}`}
              className="text-[11px] text-[color:var(--text-muted)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              Открыть
            </Link>
          </div>
        </div>

        {showBreakdown && (
          <div className="mt-1 flex flex-col gap-1.5 rounded-lg bg-[color:var(--surface-sunken)] p-3">
            {breakdown.parts.map((p) => (
              <div
                key={p.label}
                className="flex items-center gap-2 text-[11px]"
              >
                <span className="w-24 text-[color:var(--text-secondary)]">
                  {p.label}
                </span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-[color:var(--border-default)]">
                  <div
                    className="h-full bg-[color:var(--accent-primary)] transition-all"
                    style={{ width: `${p.value}%` }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-[color:var(--text-primary)]">
                  {p.value}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function CrossContextBadge({ risk }: { risk: number }) {
  const percent = Math.round(risk * 100);
  return (
    <div
      role="status"
      aria-label={`Cross-context risk ${percent} процентов`}
      title="Рилс собран из сегментов, разделённых более 5 минутами в оригинале. Проверь что смысл сохранён."
      className="mt-1 flex items-start gap-2 rounded-md border border-[color:var(--warning)]/40 bg-[color:var(--warning)]/10 px-2.5 py-1.5 text-[11px] leading-snug text-[color:var(--warning)]"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="mt-px shrink-0"
      >
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      </svg>
      <span className="flex-1">
        <span className="block font-medium">
          Cross-context — проверь перед публикацией
        </span>
        <span className="text-[color:var(--warning)]">
          Риск {percent}% · сегменты разнесены во времени или тематически.
        </span>
      </span>
    </div>
  );
}

function LikeOverlay({
  liked,
  onChange,
  disabled,
}: {
  liked: LikeState;
  onChange: (state: LikeState) => void;
  disabled: boolean;
}) {
  return (
    <div className="pointer-events-none absolute left-3 top-3 flex flex-col gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
      <button
        type="button"
        onClick={() => onChange(liked === "like" ? "none" : "like")}
        disabled={disabled}
        aria-pressed={liked === "like"}
        aria-label={liked === "like" ? "Снять лайк" : "Лайк"}
        className={`pointer-events-auto flex size-9 items-center justify-center rounded-full border backdrop-blur-md transition-all ${
          liked === "like"
            ? "border-white/40 bg-[color:var(--accent-primary)] text-white shadow-lg"
            : "border-white/15 bg-black/55 text-white hover:bg-black/75"
        }`}
      >
        <HeartIcon filled={liked === "like"} />
      </button>
      <button
        type="button"
        onClick={() => onChange(liked === "dislike" ? "none" : "dislike")}
        disabled={disabled}
        aria-pressed={liked === "dislike"}
        aria-label={liked === "dislike" ? "Убрать дизлайк" : "Дизлайк"}
        className={`pointer-events-auto flex size-9 items-center justify-center rounded-full border backdrop-blur-md transition-all ${
          liked === "dislike"
            ? "border-white/40 bg-[color:var(--danger)] text-white shadow-lg"
            : "border-white/15 bg-black/55 text-white hover:bg-black/75"
        }`}
      >
        <ThumbsDownIcon filled={liked === "dislike"} />
      </button>
    </div>
  );
}

function SelectCheckbox({
  selected,
  onToggle,
  disabled,
}: {
  selected: boolean;
  onToggle: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      disabled={disabled}
      aria-pressed={selected}
      aria-label={selected ? "Снять выбор" : "Выбрать рилс"}
      className={`absolute right-3 bottom-3 flex size-9 items-center justify-center rounded-full border backdrop-blur-md transition-opacity ${
        selected
          ? "border-white/40 bg-[color:var(--accent-primary)] text-white shadow-lg opacity-100"
          : "border-white/15 bg-black/55 text-white opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
      }`}
    >
      {selected ? (
        <svg
          width="16"
          height="16"
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
        <span className="size-4 rounded-full border-2 border-white/70" aria-hidden="true" />
      )}
    </button>
  );
}

function DeleteButton({
  onDelete,
  disabled,
  reelId,
}: {
  onDelete: () => void;
  disabled: boolean;
  reelId: string;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        if (
          typeof window !== "undefined" &&
          !window.confirm(`Удалить рилс ${reelId}? Его файл будет стёрт с диска.`)
        ) {
          return;
        }
        onDelete();
      }}
      disabled={disabled}
      aria-label={`Удалить рилс ${reelId}`}
      className="absolute left-3 bottom-3 flex size-9 items-center justify-center rounded-full border border-white/15 bg-black/55 text-white opacity-0 backdrop-blur-md transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 hover:bg-[color:var(--danger)]"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        <path d="M10 11v6" />
        <path d="M14 11v6" />
        <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
      </svg>
    </button>
  );
}

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

function ThumbsDownIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
    </svg>
  );
}

function toLikeState(raw: unknown): LikeState {
  if (raw === "like" || raw === "dislike") return raw;
  return "none";
}

function ScoreBadge({
  breakdown,
  onToggle,
  showBreakdown,
}: {
  breakdown: ViralScoreBreakdown;
  onToggle: () => void;
  showBreakdown: boolean;
}) {
  const color = colorForGrade(breakdown.grade);
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={showBreakdown}
      className="absolute right-3 top-3 flex items-baseline gap-1 rounded-xl border border-white/15 bg-black/60 px-2.5 py-1.5 text-white shadow-lg backdrop-blur-md transition-transform hover:scale-105"
      title={`Оценка ${breakdown.score} из 100 — нажми для деталей`}
    >
      <span
        className="display-serif text-2xl leading-none tracking-tight"
        style={{ color }}
      >
        {breakdown.score}
      </span>
      <span className="text-[10px] font-mono text-white/60">/100</span>
    </button>
  );
}

function colorForGrade(grade: ViralScoreBreakdown["grade"]): string {
  switch (grade) {
    case "A":
      return "#4ade80";
    case "A-":
      return "#a3e635";
    case "B":
      return "#fde047";
    case "B-":
      return "#fb923c";
    case "C":
      return "#f87171";
  }
}

function buildFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2)
    return `/api/v1/files/${jobId}/log/${encodeURIComponent(relativePath)}`;
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}
