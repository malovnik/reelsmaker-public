
import { Link } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ArtifactRead,
  type JobRead,
} from "@/lib/api";

interface Props {
  job: JobRead;
  initialReels: ArtifactRead[];
}

type Verdict = "like" | "dislike" | "skip";

const SWIPE_DISTANCE_PX = 80;
const SWIPE_VELOCITY_PX = 0.35;

export function TinderClient({ job, initialReels }: Props) {
  const [reels, setReels] = useState<ArtifactRead[]>(initialReels);
  const [index, setIndex] = useState(0);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Global playback speed для всех рилсов — сохраняется между карточками.
  // Хранится как number чтобы не выходить за допустимый HTMLMediaElement diapason.
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  // Progress воспроизведения текущего рилса (secs). Обновляется onTimeUpdate.
  const [currentTime, setCurrentTime] = useState<number>(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const touchStart = useRef<{
    x: number;
    y: number;
    t: number;
  } | null>(null);

  const current = reels[index];
  const hasNext = index < reels.length - 1;
  const isFinished = reels.length > 0 && index >= reels.length;

  const applyVerdict = useCallback(
    async (value: Verdict) => {
      if (!current || busy) return;
      setBusy(true);
      setVerdict(value);
      setError(null);
      try {
        if (value !== "skip") {
          const next = value;
          const updated = await api.updateArtifactLike(
            job.id,
            current.id,
            next,
          );
          setReels((prev) =>
            prev.map((r) => (r.id === updated.id ? updated : r)),
          );
        }
      } catch {
        setError("Не получилось сохранить оценку. Попробуй ещё раз.");
        setVerdict(null);
        setBusy(false);
        return;
      }
      window.setTimeout(() => {
        setIndex((prev) => prev + 1);
        setVerdict(null);
        setBusy(false);
      }, 320);
    },
    [busy, current, job.id],
  );

  const togglePlay = useCallback(() => {
    const el = videoRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play();
      setIsPlaying(true);
    } else {
      el.pause();
      setIsPlaying(false);
    }
  }, []);

  const goBack = useCallback(() => {
    // Вернуться к предыдущему рилсу. Не трогает like/dislike пометки
    // уже сделанные юзером — они сохраняются по reel.id. Verdict-оверлей
    // сбрасывается чтобы предыдущий рилс показывался без "галочки".
    setIndex((prev) => (prev > 0 ? prev - 1 : prev));
    setVerdict(null);
    setError(null);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        void applyVerdict("like");
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        void applyVerdict("dislike");
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        void applyVerdict("skip");
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        goBack();
      } else if (event.key === " ") {
        event.preventDefault();
        togglePlay();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [applyVerdict, goBack, togglePlay]);

  useEffect(() => {
    // Применяем global playback rate к video element. Пересоздавать нужно
    // при смене рилса (новый <video> элемент через key={current.id}) —
    // иначе rate сбрасывается на native default 1.0.
    const el = videoRef.current;
    if (el) {
      el.playbackRate = playbackRate;
    }
  }, [playbackRate, index]);

  useEffect(() => {
    // Reset play state when user navigates to next/prev reel.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsPlaying(true);
  }, [index]);

  function onTouchStart(event: React.TouchEvent) {
    const t = event.touches[0];
    if (!t) return;
    touchStart.current = { x: t.clientX, y: t.clientY, t: performance.now() };
  }

  function onTouchEnd(event: React.TouchEvent) {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start) return;
    const t = event.changedTouches[0];
    if (!t) return;
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    const dt = Math.max(1, performance.now() - start.t);
    const vx = Math.abs(dx) / dt;
    const vy = Math.abs(dy) / dt;
    const horizontal = Math.abs(dx) > Math.abs(dy);
    if (horizontal && (Math.abs(dx) > SWIPE_DISTANCE_PX || vx > SWIPE_VELOCITY_PX)) {
      void applyVerdict(dx > 0 ? "like" : "dislike");
    } else if (!horizontal && (dy > SWIPE_DISTANCE_PX || vy > SWIPE_VELOCITY_PX)) {
      void applyVerdict("skip");
    }
  }

  if (reels.length === 0) {
    return (
      <EmptyShell
        jobId={job.id}
        title="Рилсы пока не собраны"
        body="Открой обычный вид — там видно прогресс по этапам нарезки."
      />
    );
  }

  if (isFinished) {
    return (
      <EmptyShell
        jobId={job.id}
        title="Ты просмотрел всю подборку"
        body={`${reels.length} рилсов размечено. Вернись в галерею, чтобы сохранить отобранные в папку.`}
      />
    );
  }

  if (!current) return null;

  const url = buildFileUrl(job.id, current.path);
  const meta = current.meta as Record<string, unknown>;
  const duration =
    typeof meta.duration_sec === "number" ? meta.duration_sec : undefined;
  const caption =
    typeof meta.caption === "string" && meta.caption.trim().length > 0
      ? meta.caption
      : undefined;

  return (
    <main className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-black text-white">
      <header className="flex shrink-0 flex-col gap-2 px-4 py-2 text-xs">
        <div className="flex items-center justify-between">
          <Link
            to={`/jobs/${job.id}`}
            className="font-mono uppercase tracking-[0.14em] text-white/70 transition-colors hover:text-white"
          >
            ← Галерея
          </Link>
          <div className="flex items-center gap-3">
            <SpeedSelector value={playbackRate} onChange={setPlaybackRate} />
            <span className="font-mono text-white/60 tabular-nums">
              {index + 1} / {reels.length}
            </span>
          </div>
        </div>
        <div
          className="h-1 w-full overflow-hidden bg-white/10"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={reels.length}
          aria-valuenow={index}
          aria-label="Размечено рилсов"
        >
          <div
            className="h-full bg-[color:var(--gold)] transition-[width] duration-300 ease-out"
            style={{ width: `${(index / reels.length) * 100}%` }}
          />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col items-center gap-3 px-4 pb-3">
        {/* Card wrapper — забирает всё доступное по высоте. min-h-0 обязателен
            чтобы flex-item мог сжиматься ниже размера content при коротком
            viewport, иначе card + actions + hint vylazят за 100dvh. */}
        <div className="flex min-h-0 w-full flex-1 items-center justify-center">
          <div
            className={`relative aspect-[9/16] h-full max-h-full overflow-hidden rounded-none border border-white/10 bg-[color:var(--ink-2)] shadow-2xl transition-transform duration-300 ease-out ${
              verdict === "like"
                ? "rotate-3 translate-x-6 opacity-70"
                : verdict === "dislike"
                  ? "-rotate-3 -translate-x-6 opacity-70"
                  : verdict === "skip"
                    ? "translate-y-4 opacity-60"
                    : ""
            }`}
            onTouchStart={onTouchStart}
            onTouchEnd={onTouchEnd}
          >
          <video
            ref={videoRef}
            key={current.id}
            src={url}
            autoPlay
            loop
            playsInline
            controls={false}
            onClick={togglePlay}
            onTimeUpdate={(e) =>
              setCurrentTime((e.target as HTMLVideoElement).currentTime)
            }
            onLoadedMetadata={() => setCurrentTime(0)}
            className="size-full object-cover"
          />
          {caption && (
            <div className="pointer-events-none absolute inset-x-0 bottom-20 px-4 text-center">
              <p className="rounded-lg bg-black/60 px-3 py-2 text-sm font-medium text-white backdrop-blur">
                {caption}
              </p>
            </div>
          )}
          {duration !== undefined && (
            <span className="absolute left-3 top-3 rounded-none bg-black/60 px-2 py-0.5 font-mono text-[11px] tabular-nums text-white/85 backdrop-blur">
              {formatClock(currentTime)} / {formatClock(duration)}
            </span>
          )}
          {duration !== undefined && duration > 0 && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-white/10">
              <div
                className="h-full bg-white/70 transition-[width] duration-150 ease-linear"
                style={{
                  width: `${Math.min(100, (currentTime / duration) * 100)}%`,
                }}
              />
            </div>
          )}
          {!isPlaying && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <span className="rounded-none border-2 border-white/60 px-4 py-1 text-xs uppercase tracking-[0.2em] text-white/80">
                Пауза
              </span>
            </div>
          )}
          <VerdictOverlay verdict={verdict} />
          </div>
        </div>

        {error && (
          <p className="shrink-0 text-xs text-[color:var(--chi)]">{error}</p>
        )}

        <div className="flex shrink-0 items-center gap-5">
          <ActionButton
            onClick={() => applyVerdict("dislike")}
            disabled={busy}
            tone="danger"
            label="Не нра"
            hotkey="←"
            icon={
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            }
          />
          <ActionButton
            onClick={() => applyVerdict("skip")}
            disabled={busy}
            tone="neutral"
            label="Пропуск"
            hotkey="↓"
            icon={
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            }
          />
          <ActionButton
            onClick={() => applyVerdict("like")}
            disabled={busy}
            tone="accent"
            label="Нра"
            hotkey="→"
            icon={
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="currentColor"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            }
          />
        </div>

        <div className="shrink-0 text-center text-[11px] text-white/50">
          ←/→ — dislike/like · ↓ — пропуск · ↑ — назад ·{" "}
          <kbd className="rounded border border-white/20 px-1.5 py-0.5 font-mono">
            Space
          </kbd>{" "}
          пауза
          {hasNext && (
            <span className="ml-3 font-mono uppercase tracking-[0.12em] text-white/40">
              · {reels.length - index - 1} впереди
            </span>
          )}
        </div>
      </div>
    </main>
  );
}

function ActionButton({
  onClick,
  disabled,
  tone,
  label,
  icon,
  hotkey,
}: {
  onClick: () => void;
  disabled: boolean;
  tone: "danger" | "neutral" | "accent";
  label: string;
  icon: React.ReactNode;
  hotkey: string;
}) {
  const palette = {
    danger:
      "border border-[color:var(--chi,#8B2500)] bg-transparent text-[color:var(--chi,#8B2500)] hover:bg-[color:var(--chi,#8B2500)] hover:text-white",
    neutral:
      "border border-white/20 bg-transparent text-white/70 hover:bg-white/10 hover:text-white",
    accent:
      "border border-[color:var(--gold)] bg-[color:var(--gold)] text-[color:var(--ink)] hover:bg-[color:var(--accent-bright)]",
  }[tone];
  const size = tone === "neutral" ? "size-14" : "size-16";
  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        className={`${size} flex items-center justify-center rounded-none shadow-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50 active:translate-y-px ${palette}`}
      >
        {icon}
      </button>
      <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-white/50">
        {hotkey}
      </span>
    </div>
  );
}

function VerdictOverlay({ verdict }: { verdict: Verdict | null }) {
  if (!verdict) return null;
  const config: Record<Verdict, { bg: string; label: string }> = {
    like: {
      bg: "bg-[color:var(--gold)]/85 text-[color:var(--ink)]",
      label: "НРА",
    },
    dislike: {
      bg: "bg-[color:var(--chi,#8B2500)]/85 text-white",
      label: "НЕ НРА",
    },
    skip: {
      bg: "bg-[color:var(--mute)]/70 text-[color:var(--ink)]",
      label: "ПРОПУСК",
    },
  };
  const { bg, label } = config[verdict];
  return (
    <div
      className={`pointer-events-none absolute inset-0 flex items-center justify-center ${bg}`}
    >
      <span className="text-5xl font-black uppercase tracking-widest">
        {label}
      </span>
    </div>
  );
}

function EmptyShell({
  jobId,
  title,
  body,
}: {
  jobId: string;
  title: string;
  body: string;
}) {
  return (
    <main className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-black px-6 text-center text-white">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="max-w-sm text-sm text-white/70">{body}</p>
      <Link
        to={`/jobs/${jobId}`}
        className="inline-flex min-h-11 items-center rounded-none border border-[color:var(--gold)] bg-[color:var(--gold)] px-5 text-sm font-semibold text-[color:var(--ink)] transition-colors hover:bg-[color:var(--accent-bright)]"
      >
        Вернуться в галерею
      </Link>
    </main>
  );
}

const PLAYBACK_SPEEDS: readonly number[] = [1, 1.5, 2] as const;

function SpeedSelector({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div
      className="flex items-center rounded-none border border-white/15 bg-white/5 p-0.5 font-mono text-[11px]"
      role="group"
      aria-label="Скорость воспроизведения"
    >
      {PLAYBACK_SPEEDS.map((speed) => {
        const active = value === speed;
        return (
          <button
            key={speed}
            type="button"
            onClick={() => onChange(speed)}
            className={`rounded-none px-2.5 py-0.5 tabular-nums transition-colors ${
              active
                ? "bg-white text-black"
                : "text-white/60 hover:text-white/90"
            }`}
            aria-pressed={active}
          >
            {speed}×
          </button>
        );
      })}
    </div>
  );
}

function formatClock(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function buildFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2)
    return `/api/v1/files/${jobId}/log/${encodeURIComponent(relativePath)}`;
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}
