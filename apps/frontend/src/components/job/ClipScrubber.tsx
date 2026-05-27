
import { useImperativeHandle, useRef, useState, forwardRef } from "react";

interface Props {
  videoUrl: string;
  onSeek?: (time: number) => void;
  onTimeUpdate?: (time: number) => void;
}

export interface ClipScrubberHandle {
  seek: (time: number) => void;
}

export const ClipScrubber = forwardRef<ClipScrubberHandle, Props>(
  function ClipScrubber({ videoUrl, onSeek, onTimeUpdate }, ref) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);

    useImperativeHandle(ref, () => ({
      seek(time: number) {
        if (videoRef.current) {
          videoRef.current.currentTime = time;
          setCurrentTime(time);
        }
      },
    }));

    const handleTimeUpdate = () => {
      if (!videoRef.current) return;
      const t = videoRef.current.currentTime;
      setCurrentTime(t);
      onTimeUpdate?.(t);
    };

    const onSeekBar = (e: React.ChangeEvent<HTMLInputElement>) => {
      const t = Number(e.target.value);
      if (videoRef.current) videoRef.current.currentTime = t;
      setCurrentTime(t);
      onSeek?.(t);
    };

    const togglePlay = () => {
      if (!videoRef.current) return;
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
      } else {
        void videoRef.current.play();
        setIsPlaying(true);
      }
    };

    return (
      <div className="flex flex-col gap-3">
        <video
          ref={videoRef}
          src={videoUrl}
          className="aspect-[9/16] w-full max-w-md rounded-xl bg-black"
          playsInline
          preload="metadata"
          onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          onTimeUpdate={handleTimeUpdate}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
        />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={togglePlay}
            aria-label={isPlaying ? "Пауза" : "Воспроизвести"}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-none bg-[color:var(--accent-primary)] text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)]"
          >
            {isPlaying ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>
          <div className="flex-1">
            <input
              type="range"
              min={0}
              max={duration || 1}
              step={0.1}
              value={currentTime}
              onChange={onSeekBar}
              aria-label="Позиция воспроизведения"
              className="h-1 w-full cursor-pointer appearance-none rounded-none bg-[color:var(--border-default)] accent-[color:var(--accent-primary)]"
            />
            <div className="mt-1 flex justify-between font-mono text-[11px] tabular-nums text-[color:var(--text-muted)]">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>
        </div>
      </div>
    );
  },
);

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
