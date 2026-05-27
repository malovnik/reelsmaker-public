
import { useMemo } from "react";
import type { ArtifactRead, JobRead } from "@/lib/api";
import { computeViralScore, viralInputFromMeta } from "@/lib/viralScore";

interface Props {
  job: JobRead;
  reels: ArtifactRead[];
}

interface Marker {
  id: number;
  startPct: number;
  widthPct: number;
  score: number;
  liked: "none" | "like" | "dislike";
}

export function HeatmapBar({ job, reels }: Props) {
  const duration = job.source_duration_sec ?? 0;
  const markers = useMemo<Marker[]>(() => {
    if (duration <= 0) return [];
    return reels
      .map((reel) => {
        const meta = reel.meta as Record<string, unknown>;
        const startRaw =
          typeof meta.source_start_sec === "number"
            ? meta.source_start_sec
            : typeof meta.start_sec === "number"
              ? meta.start_sec
              : null;
        const reelDuration =
          typeof meta.duration_sec === "number" ? meta.duration_sec : 0;
        if (startRaw === null) return null;
        const viral = computeViralScore(viralInputFromMeta(meta));
        const liked =
          meta.liked === "like" || meta.liked === "dislike"
            ? (meta.liked as "like" | "dislike")
            : "none";
        return {
          id: reel.id,
          startPct: (startRaw / duration) * 100,
          widthPct: Math.max(0.4, (reelDuration / duration) * 100),
          score: viral.score,
          liked,
        } as Marker;
      })
      .filter((m): m is Marker => m !== null);
  }, [duration, reels]);

  if (duration <= 0 || markers.length === 0) return null;

  const durationLabel = formatDuration(duration);

  return (
    <div className="surface-card p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div className="mono micro mute">
          тепловая карта интереса Reelibra
        </div>
        <div className="mono micro mute tabular-nums">
          0:00 ——— {durationLabel}
        </div>
      </div>
      <div className="relative h-12 overflow-hidden rounded-[4px] bg-[color:var(--ink-3)]">
        {[...Array(120)].map((_, i) => {
          const h = 20 + Math.abs(Math.sin(i * 0.7)) * 20 + ((i * 13) % 9);
          return (
            <div
              key={`wave-${i}`}
              style={{
                position: "absolute",
                left: `${(i / 120) * 100}%`,
                width: "0.6%",
                bottom: "50%",
                transform: "translateY(50%)",
                height: h,
                background: "oklch(0.32 0.01 260)",
              }}
            />
          );
        })}
        {markers.map((m) => {
          const color =
            m.liked === "like"
              ? "var(--gold)"
              : m.liked === "dislike"
                ? "var(--ember)"
                : m.score >= 90
                  ? "var(--gold)"
                  : m.score >= 75
                    ? "var(--gold-dim)"
                    : "var(--mute-2)";
          const opacity = m.liked === "dislike" ? 0.4 : 0.8;
          return (
            <div
              key={m.id}
              title={`${m.score}/100`}
              style={{
                position: "absolute",
                top: 0,
                bottom: 0,
                left: `${m.startPct}%`,
                width: `${Math.max(m.widthPct, 0.6)}%`,
                background: color,
                opacity,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

function formatDuration(sec: number): string {
  const total = Math.floor(sec);
  const mm = Math.floor(total / 60);
  const ss = total - mm * 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}
