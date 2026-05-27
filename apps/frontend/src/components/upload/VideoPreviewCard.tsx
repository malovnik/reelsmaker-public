
import { useEffect, useMemo, useState } from "react";

interface Props {
  file: File;
  onRemove: () => void;
}

interface VideoMetadata {
  duration_sec: number;
  width: number;
  height: number;
}

export function VideoPreviewCard({ file, onRemove }: Props) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  const [meta, setMeta] = useState<VideoMetadata | null>(null);

  useEffect(() => {
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [url]);

  const onLoaded = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const video = e.currentTarget;
    setMeta({
      duration_sec: video.duration,
      width: video.videoWidth,
      height: video.videoHeight,
    });
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 sm:flex-row">
      <video
        src={url}
        className="w-full max-w-[200px] rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]"
        controls
        preload="metadata"
        onLoadedMetadata={onLoaded}
      />
      <div className="flex flex-1 flex-col gap-1.5 text-sm">
        <div className="break-all font-medium text-[color:var(--text-primary)]">
          {file.name}
        </div>
        <div className="font-mono text-[11px] text-[color:var(--text-muted)]">
          {(file.size / (1024 * 1024)).toFixed(1)} МБ
          {meta ? ` · ${meta.width}×${meta.height}` : ""}
          {meta ? ` · ${formatDuration(meta.duration_sec)}` : ""}
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="mt-2 self-start rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-canvas)] px-3 py-1 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--danger)] hover:text-[color:var(--danger)]"
        >
          Убрать файл
        </button>
      </div>
    </div>
  );
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
