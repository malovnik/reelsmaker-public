
import type { RefObject } from "react";
import type { VideoAsset } from "@/lib/api";

interface Props {
  assets: VideoAsset[];
  assetUploadRef: RefObject<HTMLInputElement | null>;
  assetName: string;
  onAssetNameChange: (value: string) => void;
  onUploadAsset: () => void;
  uploadingAsset: boolean;
  onDeleteAsset: (id: number) => void;
}

export function AssetsColumn({
  assets,
  assetUploadRef,
  assetName,
  onAssetNameChange,
  onUploadAsset,
  uploadingAsset,
  onDeleteAsset,
}: Props) {
  return (
    <section className="surface-card flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--mute)]">
          Ролики
        </h2>
        <span className="font-mono text-[11px] text-[color:var(--mute)]">
          {assets.length}
        </span>
      </div>

      <div className="flex flex-col gap-2 rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] p-3">
        <input
          ref={assetUploadRef}
          type="file"
          accept=".mp4,.mov,.mkv,.webm,.m4v"
          className="text-xs text-[color:var(--mute-2)] file:mr-2 file:rounded file:border-0 file:bg-[color:var(--ink)] file:px-2 file:py-1 file:text-xs file:text-[color:var(--paper)] hover:file:bg-[color:var(--line)]"
        />
        <input
          type="text"
          placeholder="Название (например, интро v1)"
          value={assetName}
          onChange={(e) => onAssetNameChange(e.target.value)}
          className="rounded-none border border-[color:var(--line)] bg-[color:var(--ink)] px-2 py-1 text-xs text-[color:var(--paper)] outline-none focus:border-[color:var(--gold)]"
        />
        <button
          onClick={onUploadAsset}
          disabled={uploadingAsset}
          type="button"
          className="rounded-none bg-[color:var(--gold)] px-2 py-1 text-xs font-semibold text-[color:var(--ink)] transition-colors hover:bg-[color:var(--gold-dim)] disabled:cursor-not-allowed disabled:bg-[color:var(--ink-3)] disabled:text-[color:var(--mute-2)]"
        >
          {uploadingAsset ? "Загружаем…" : "Загрузить"}
        </button>
      </div>

      <div className="flex max-h-[60vh] flex-col gap-1.5 overflow-y-auto">
        {assets.length === 0 && (
          <p className="text-[11px] text-[color:var(--mute)]">
            Пока нет роликов. Загрузи интро, аутро или заставку через форму
            выше.
          </p>
        )}
        {assets.map((a) => (
          <div
            key={a.id}
            className="flex items-start justify-between gap-2 rounded-none border border-[color:var(--line)] bg-[color:var(--ink)] p-2"
          >
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-xs font-medium text-[color:var(--paper)]">
                {a.name}
              </span>
              <span className="font-mono text-[10px] text-[color:var(--mute)]">
                {a.duration_sec.toFixed(1)} с · {a.width}×{a.height}
              </span>
              <span className="font-mono text-[10px] text-[color:var(--mute-2)]">
                {(a.file_size_bytes / 1024 / 1024).toFixed(1)} МБ
              </span>
            </div>
            <button
              onClick={() => onDeleteAsset(a.id)}
              type="button"
              aria-label="Удалить ролик"
              className="text-[10px] text-[color:var(--mute)] transition-colors hover:text-[color:var(--danger)]"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
