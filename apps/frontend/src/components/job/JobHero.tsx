
import type { JobRead, VisionProfile } from "@/lib/api";
import type { TranscriptCacheState } from "@/lib/sse";
import { PROFILE_LABELS } from "@/components/ProfileSelector";
import { TranscriptCacheBadge } from "@/components/TranscriptCacheBadge";

const PROFILE_COLOR: Record<VisionProfile, string> = {
  talking_head: "var(--profile-talking-head)",
  fashion: "var(--profile-fashion)",
  travel: "var(--profile-travel)",
  screencast: "var(--profile-screencast)",
  custom: "var(--profile-custom)",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "в очереди",
  running: "обрабатывается",
  done: "готово",
  error: "ошибка",
  cancelled: "отменено",
};

interface Props {
  job: JobRead;
  progress: number;
  cacheState: TranscriptCacheState | null;
  wordCount?: number;
  wpm?: number;
  videoHash?: string;
}

export function JobHero({
  job,
  progress,
  cacheState,
  wordCount,
  wpm,
  videoHash,
}: Props) {
  const color = PROFILE_COLOR[job.vision_profile] ?? PROFILE_COLOR.custom;
  const label = PROFILE_LABELS[job.vision_profile] ?? job.vision_profile;
  const statusLabel = STATUS_LABEL[job.status] ?? job.status;

  return (
    <header className="surface-card flex flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="display-serif text-3xl leading-tight tracking-tight text-[color:var(--text-primary)] sm:text-4xl">
            {job.source_filename}
          </h1>
          <p className="font-mono text-[11px] text-[color:var(--text-muted)]">
            {job.id.slice(0, 8)} · {job.transcriber} · {job.llm_provider}/
            {job.llm_model} · {job.target_aspect}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium"
            style={{
              color,
              borderColor: color,
              backgroundColor: "transparent",
            }}
          >
            <span
              aria-hidden="true"
              className="size-1.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            {label}
          </span>
          <TranscriptCacheBadge
            state={cacheState}
            wordCount={wordCount}
            wpm={wpm}
            videoHash={videoHash}
          />
          <StatusPill status={job.status} label={statusLabel} />
        </div>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-[color:var(--text-muted)]">
          <span className="uppercase tracking-[0.1em]">Прогресс</span>
          <span className="font-mono text-[color:var(--text-primary)]">
            {progress}%
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
          <div
            className={[
              "h-full transition-all duration-500",
              job.status === "error"
                ? "bg-[color:var(--danger)]"
                : job.status === "done"
                  ? "bg-[color:var(--success)]"
                  : "gradient-accent",
            ].join(" ")}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {typeof job.total_generation_sec === "number" &&
        job.total_generation_sec > 0 && (
          <div className="flex items-center gap-2 text-[11px] text-[color:var(--text-muted)]">
            <span className="uppercase tracking-[0.1em]">
              Общее время генерации
            </span>
            <span className="font-mono tabular-nums text-[color:var(--text-primary)]">
              {formatDuration(job.total_generation_sec)}
            </span>
          </div>
        )}

      {job.error && (
        <div className="rounded-lg border border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 p-3 text-xs text-[color:var(--danger)]">
          {job.error}
        </div>
      )}
    </header>
  );
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)} с`;
  const minutes = Math.floor(sec / 60);
  const seconds = Math.round(sec - minutes * 60);
  if (minutes < 60) return `${minutes} мин ${seconds.toString().padStart(2, "0")} с`;
  const hours = Math.floor(minutes / 60);
  const remMin = minutes - hours * 60;
  return `${hours} ч ${remMin.toString().padStart(2, "0")} мин`;
}

function StatusPill({ status, label }: { status: string; label: string }) {
  const tone: Record<string, string> = {
    pending:
      "bg-[color:var(--surface-sunken)] text-[color:var(--text-muted)]",
    running: "bg-[color:var(--warning)]/10 text-[color:var(--warning)]",
    done: "bg-[color:var(--success)]/10 text-[color:var(--success)]",
    error: "bg-[color:var(--danger)]/10 text-[color:var(--danger)]",
    cancelled:
      "bg-[color:var(--surface-sunken)] text-[color:var(--text-muted)]",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
        tone[status] ?? tone.pending
      }`}
    >
      {status === "running" && (
        <span
          aria-hidden="true"
          className="size-1.5 animate-pulse rounded-full bg-[color:var(--warning)]"
        />
      )}
      {label}
    </span>
  );
}
