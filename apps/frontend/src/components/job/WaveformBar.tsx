
import { useEffect, useRef } from "react";

interface Props {
  audioUrl: string;
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
}

const BUCKETS = 240;

export function WaveformBar({
  audioUrl,
  currentTime,
  duration,
  onSeek,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    let audioCtx: AudioContext | null = null;
    async function draw() {
      try {
        const res = await fetch(audioUrl);
        if (!res.ok) return;
        const buf = await res.arrayBuffer();
        const AudioCtxCtor =
          window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;
        if (!AudioCtxCtor) return;
        audioCtx = new AudioCtxCtor();
        const decoded = await audioCtx.decodeAudioData(buf.slice(0));
        if (cancelled || !canvasRef.current) return;
        const raw = decoded.getChannelData(0);
        const step = Math.max(1, Math.floor(raw.length / BUCKETS));
        const data: number[] = [];
        for (let i = 0; i < BUCKETS; i++) {
          let max = 0;
          const base = i * step;
          for (let j = 0; j < step; j++) {
            const v = Math.abs(raw[base + j] ?? 0);
            if (v > max) max = v;
          }
          data.push(max);
        }
        const canvas = canvasRef.current;
        const cctx = canvas.getContext("2d");
        if (!cctx) return;
        const w = canvas.width;
        const h = canvas.height;
        cctx.clearRect(0, 0, w, h);
        cctx.fillStyle =
          getComputedStyle(canvas).getPropertyValue("--mute").trim() ||
          "#8A8278";
        const bw = w / BUCKETS;
        for (let i = 0; i < BUCKETS; i++) {
          const bh = (data[i] ?? 0) * h;
          cctx.fillRect(i * bw, (h - bh) / 2, bw * 0.7, bh);
        }
      } catch {
        // graceful degrade — скрываем волну, компонент остаётся seekbar'ом
      } finally {
        if (audioCtx && audioCtx.state !== "closed") {
          void audioCtx.close().catch(() => undefined);
        }
      }
    }
    void draw();
    return () => {
      cancelled = true;
    };
  }, [audioUrl]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (duration <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    onSeek((x / rect.width) * duration);
  };

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={480}
        height={60}
        className="w-full cursor-pointer rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]"
        onClick={onClick}
        aria-label="Аудио-волна рилса, клик = перейти к моменту"
      />
      <div
        className="pointer-events-none absolute inset-y-0 left-0 rounded-l-lg bg-[color:var(--accent-primary)]/20"
        style={{ width: `${progressPct}%` }}
        aria-hidden="true"
      />
    </div>
  );
}
