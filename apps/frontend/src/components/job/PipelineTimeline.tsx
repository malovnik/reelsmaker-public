
interface StageDef {
  key: string;
  label: string;
}

export const PIPELINE_STAGES: StageDef[] = [
  { key: "ingest", label: "Проверка видео" },
  { key: "proxy_generate", label: "Подготовка копии" },
  { key: "transcribe", label: "Распознавание речи" },
  { key: "translate", label: "Перевод" },
  { key: "silence_cut", label: "Удаление пауз" },
  { key: "analyze", label: "Поиск лучших моментов" },
  { key: "render", label: "Сборка рилсов" },
  { key: "done", label: "Готово" },
];

interface Props {
  currentStage: string;
  status: string;
  progress: number;
  message?: string;
  stageDurations?: Record<string, number> | null;
}

export function PipelineTimeline({
  currentStage,
  status,
  progress,
  message,
  stageDurations,
}: Props) {
  const currentIdx = PIPELINE_STAGES.findIndex((s) => s.key === currentStage);
  const isError = status === "error";
  const isDone = status === "done";

  return (
    <ol className="flex flex-col" role="list">
      {PIPELINE_STAGES.map((stage, idx) => {
        const active = idx === currentIdx && !isDone;
        const past = isDone ? true : idx < currentIdx;
        const pending = !active && !past;
        const isLast = idx === PIPELINE_STAGES.length - 1;
        const durationSec = stageDurations?.[stage.key];

        return (
          <li key={stage.key} className="relative flex gap-4">
            <div className="relative flex shrink-0 flex-col items-center">
              <StageMarker
                active={active}
                past={past}
                pending={pending}
                error={active && isError}
              />
              {!isLast && (
                <div
                  className={[
                    "w-px flex-1",
                    past
                      ? "bg-[color:var(--accent-primary)]"
                      : "bg-[color:var(--border-subtle)]",
                  ].join(" ")}
                  style={{ minHeight: active ? "56px" : "28px" }}
                />
              )}
            </div>

            <div className="flex-1 pb-5">
              <div className="flex items-baseline gap-3">
                <span
                  className={[
                    "text-sm font-medium",
                    active
                      ? "text-[color:var(--text-primary)]"
                      : past
                        ? "text-[color:var(--text-secondary)]"
                        : "text-[color:var(--text-muted)]",
                  ].join(" ")}
                >
                  {stage.label}
                </span>
                {active && (
                  <span className="font-mono text-[11px] text-[color:var(--accent-primary)]">
                    {progress}%
                  </span>
                )}
                {past && (
                  <span aria-hidden="true" className="text-xs text-[color:var(--success)]">
                    ✓
                  </span>
                )}
                {past && typeof durationSec === "number" && durationSec > 0 && (
                  <span className="ml-auto font-mono tabular-nums text-[11px] text-[color:var(--text-muted)]">
                    {formatStageDuration(durationSec)}
                  </span>
                )}
              </div>
              {active && message && (
                <p className="mt-1 text-xs text-[color:var(--text-muted)]">
                  {message}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function formatStageDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)} с`;
  const minutes = Math.floor(sec / 60);
  const seconds = Math.round(sec - minutes * 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function StageMarker({
  active,
  past,
  pending,
  error,
}: {
  active: boolean;
  past: boolean;
  pending: boolean;
  error: boolean;
}) {
  if (error) {
    return (
      <div
        className="flex size-5 shrink-0 items-center justify-center rounded-full is-round bg-[color:var(--danger)] text-[color:var(--paper)]"
        aria-hidden="true"
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
        >
          <line x1="6" y1="6" x2="18" y2="18" />
          <line x1="18" y1="6" x2="6" y2="18" />
        </svg>
      </div>
    );
  }
  if (past) {
    return (
      <div
        className="flex size-5 shrink-0 items-center justify-center rounded-full is-round bg-[color:var(--accent-primary)] text-[color:var(--accent-on-primary)]"
        aria-hidden="true"
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
    );
  }
  if (active) {
    return (
      <div className="relative flex size-5 shrink-0 items-center justify-center" aria-hidden="true">
        <span className="absolute size-5 rounded-full is-round bg-[color:var(--accent-primary)] opacity-25 animate-ping" />
        <span className="relative size-3 rounded-full is-round bg-[color:var(--accent-primary)]" />
      </div>
    );
  }
  if (pending) {
    return (
      <div
        className="size-5 shrink-0 rounded-full is-round border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
        aria-hidden="true"
      />
    );
  }
  return null;
}
