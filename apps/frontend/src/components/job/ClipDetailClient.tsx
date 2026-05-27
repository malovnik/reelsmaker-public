
import { Link } from "react-router-dom";
import { useMemo, useRef, useState, useTransition } from "react";
import { api, type ArtifactRead, type JobRead } from "@/lib/api";
import {
  computeViralScore,
  viralInputFromMeta,
  type ViralScoreBreakdown,
} from "@/lib/viralScore";
import { ClipScrubber, type ClipScrubberHandle } from "@/components/job/ClipScrubber";
import { WaveformBar } from "@/components/job/WaveformBar";
import { CaptionsEditor } from "@/components/job/CaptionsEditor";
import { ExportDialog } from "@/components/job/ExportDialog";

interface Props {
  job: JobRead;
  reel: ArtifactRead;
  siblings: ArtifactRead[];
}

type LikeState = "none" | "like" | "dislike";

export function ClipDetailClient({ job, reel: initialReel, siblings }: Props) {
  const [reel, setReel] = useState<ArtifactRead>(initialReel);
  const [isPending, startTransition] = useTransition();

  const meta = reel.meta as Record<string, unknown>;
  const reelId = String(meta.reel_id ?? reel.id);
  const duration =
    typeof meta.duration_sec === "number" ? meta.duration_sec : undefined;
  const caption = typeof meta.caption === "string" ? meta.caption : undefined;
  const startSec =
    typeof meta.source_start_sec === "number"
      ? meta.source_start_sec
      : typeof meta.start_sec === "number"
        ? meta.start_sec
        : null;
  const breakdown = useMemo(
    () => computeViralScore(viralInputFromMeta(meta)),
    [meta],
  );
  const liked: LikeState =
    meta.liked === "like" || meta.liked === "dislike"
      ? (meta.liked as LikeState)
      : "none";
  const url = buildFileUrl(job.id, reel.path);

  const scrubberRef = useRef<ClipScrubberHandle | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const clipDurationSec = typeof duration === "number" ? duration : 0;
  const [exportOpen, setExportOpen] = useState(false);

  const currentIndex = siblings.findIndex((s) => s.id === reel.id);
  const prev = currentIndex > 0 ? siblings[currentIndex - 1] : null;
  const next =
    currentIndex >= 0 && currentIndex < siblings.length - 1
      ? siblings[currentIndex + 1]
      : null;

  const total = siblings.length;

  function setLike(newLike: LikeState) {
    const prev = liked;
    startTransition(async () => {
      try {
        const updated = await api.updateArtifactLike(
          job.id,
          reel.id,
          newLike,
        );
        setReel(updated);
      } catch {
        // revert by re-reading
        setReel((current) => ({
          ...current,
          meta: { ...(current.meta as object), liked: prev },
        }));
      }
    });
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <Link
          to={`/jobs/${job.id}`}
          className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
        >
          ← В библиотеку
        </Link>
        <span className="mono micro mute tabular-nums">
          {currentIndex + 1} / {total}
        </span>
      </div>

      <header className="flex flex-col gap-3">
        <div className="mono micro mute">клип · {reelId}</div>
        <h1 className="display-serif text-[40px] leading-[1.08] tracking-[-0.02em] text-[color:var(--paper)] sm:text-[48px]">
          {caption ?? job.source_filename}
        </h1>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-[color:var(--mute-2)]">
          {duration !== undefined && (
            <span className="mono tabular-nums">{duration.toFixed(1)} с</span>
          )}
          {startSec !== null && (
            <span className="mono tabular-nums">из {formatTime(startSec)}</span>
          )}
          <span>{job.source_filename}</span>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-8 lg:grid-cols-[auto_1fr]">
        <div className="flex flex-col gap-3">
          <ClipScrubber
            ref={scrubberRef}
            videoUrl={url}
            onTimeUpdate={setPlayhead}
          />
          <WaveformBar
            audioUrl={url}
            currentTime={playhead}
            duration={clipDurationSec}
            onSeek={(t) => scrubberRef.current?.seek(t)}
          />
        </div>

        <div className="flex flex-col gap-6">
          <ScoreBlock breakdown={breakdown} />

          <div className="surface-card p-5">
            <div className="divider mb-4">оценка зрителя</div>
            <div className="flex gap-3">
              <LikeButton
                tone="accent"
                active={liked === "like"}
                label="Нравится"
                disabled={isPending}
                onClick={() => setLike(liked === "like" ? "none" : "like")}
              />
              <LikeButton
                tone="danger"
                active={liked === "dislike"}
                label="Не нравится"
                disabled={isPending}
                onClick={() =>
                  setLike(liked === "dislike" ? "none" : "dislike")
                }
              />
            </div>
          </div>

          {caption && (
            <div className="surface-card p-5">
              <div className="divider mb-3">подпись</div>
              <p className="text-[14px] leading-relaxed text-[color:var(--paper)]">
                {caption}
              </p>
            </div>
          )}

          <div className="surface-card p-5">
            <div className="divider mb-3">субтитры (ASS)</div>
            <CaptionsEditor jobId={job.id} reelId={reelId} />
          </div>

          <div className="surface-card flex items-center justify-between gap-3 p-5">
            <div className="flex flex-col">
              <span className="display-serif text-[18px] leading-tight text-[color:var(--paper)]">
                Экспорт для площадок
              </span>
              <span className="text-[12px] text-[color:var(--mute-2)]">
                Выбор пресета: TikTok, Reels, Shorts, X
              </span>
            </div>
            <button
              type="button"
              onClick={() => setExportOpen(true)}
              className="btn btn-primary"
            >
              Экспорт
            </button>
          </div>

          <div className="flex items-center justify-between">
            {prev ? (
              <Link
                to={`/jobs/${job.id}/reels/${prev.id}`}
                className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
              >
                ← Предыдущий
              </Link>
            ) : (
              <span />
            )}
            {next ? (
              <Link
                to={`/jobs/${job.id}/reels/${next.id}`}
                className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
              >
                Следующий →
              </Link>
            ) : (
              <span />
            )}
          </div>
        </div>
      </section>

      {exportOpen && (
        <ExportDialog
          jobId={job.id}
          reelId={reelId}
          onClose={() => setExportOpen(false)}
        />
      )}
    </div>
  );
}

function ScoreBlock({ breakdown }: { breakdown: ViralScoreBreakdown }) {
  return (
    <div className="surface-card p-5">
      <div className="divider mb-4">эвристика длины и ритма</div>
      <p className="mb-4 text-[11px] leading-relaxed text-[color:var(--mute-2)]">
        Прикидка на клиенте по длительности и ритму рилса (best-practice
        Instagram Reels). Это не оценка движка нарезки — ориентир, а не вердикт.
      </p>
      <div className="flex items-start gap-6">
        <div
          className="score-ring"
          style={{
            width: 96,
            height: 96,
            background: `conic-gradient(var(--gold) ${breakdown.score}%, var(--ink-3) 0)`,
          }}
        >
          <span style={{ fontSize: 36 }}>{breakdown.score}</span>
        </div>
        <div className="flex flex-1 flex-col gap-2">
          {breakdown.parts.map((p) => (
            <div
              key={p.label}
              className="grid grid-cols-[80px_1fr_28px] items-center gap-3 text-[11px]"
            >
              <span className="mono mute">{p.label}</span>
              <div className="range-track">
                <span style={{ width: `${p.value}%` }} />
              </div>
              <span className="mono tabular-nums text-right text-[color:var(--paper)]">
                {p.value}
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-4 text-[12px] text-[color:var(--paper-dim)]">
        {breakdown.comment}
      </p>
    </div>
  );
}

function LikeButton({
  tone,
  active,
  label,
  disabled,
  onClick,
}: {
  tone: "accent" | "danger";
  active: boolean;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  const baseClasses =
    "flex-1 rounded-md border px-4 py-3 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60";
  const toneClasses = active
    ? tone === "accent"
      ? "border-[color:var(--gold)] bg-[color:var(--gold)] text-[color:var(--ink)]"
      : "border-[color:var(--danger)] bg-[color:var(--danger)] text-[color:var(--paper)]"
    : "border-[color:var(--line)] bg-[color:var(--ink-2)] text-[color:var(--paper-dim)] hover:border-[color:var(--mute)] hover:text-[color:var(--paper)]";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`${baseClasses} ${toneClasses}`}
    >
      {label}
    </button>
  );
}

function buildFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2)
    return `/api/v1/files/${jobId}/log/${encodeURIComponent(relativePath)}`;
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}

function formatTime(sec: number): string {
  const total = Math.floor(sec);
  const mm = Math.floor(total / 60);
  const ss = total - mm * 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}
