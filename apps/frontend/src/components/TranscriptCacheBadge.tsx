
import type { TranscriptCacheState } from "@/lib/sse";

interface Props {
  state: TranscriptCacheState | null;
  wordCount?: number;
  wpm?: number;
  videoHash?: string;
}

/**
 * Индикатор состояния кэша транскриптов.
 *
 *  — hit: транскрипт взят из кэша, распознавание речи пропущено.
 *  — miss: запускается распознавание речи.
 *  — null: статус ещё не получен.
 */
export function TranscriptCacheBadge({
  state,
  wordCount,
  wpm,
  videoHash,
}: Props) {
  if (state === null) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1 text-[11px] font-medium text-[color:var(--text-muted)]"
        title="Статус кэша транскриптов"
      >
        <span
          aria-hidden="true"
          className="size-1.5 rounded-full bg-[color:var(--text-muted)]"
        />
        кэш: проверяю
      </span>
    );
  }

  if (state === "hit") {
    const title = videoHash
      ? `Кэш сработал · ${videoHash.slice(0, 12)}…${
          wordCount ? ` · ${wordCount} слов` : ""
        }${wpm ? ` · ${wpm} слов/мин` : ""}`
      : "Транскрипт взят из кэша, распознавание речи не запускалось.";
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--accent-primary)] bg-[color:var(--accent-primary-subtle)] px-3 py-1 text-[11px] font-semibold text-[color:var(--accent-primary-hover)]"
        title={title}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
        Из кэша
        {wordCount !== undefined && (
          <span className="ml-0.5 font-mono text-[10px] font-normal text-[color:var(--accent-primary)]">
            {wordCount} слов
          </span>
        )}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--warning)]/60 bg-[color:var(--warning)]/10 px-3 py-1 text-[11px] font-medium text-[color:var(--warning)]"
      title="Запускается распознавание речи"
    >
      <span
        aria-hidden="true"
        className="size-1.5 animate-pulse rounded-full bg-[color:var(--warning)]"
      />
      распознаю речь
    </span>
  );
}
