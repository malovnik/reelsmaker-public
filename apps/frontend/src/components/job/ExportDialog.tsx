
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  jobId: string;
  reelId: string;
  onClose: () => void;
}

interface PresetOption {
  id: string;
  label: string;
  hint: string;
}

const PRESETS: PresetOption[] = [
  { id: "tiktok", label: "TikTok", hint: "6 Мбит · -14 LUFS" },
  { id: "reels", label: "Instagram Reels", hint: "5 Мбит · -14 LUFS" },
  { id: "shorts", label: "YouTube Shorts", hint: "8 Мбит · -14 LUFS" },
  { id: "x", label: "X / Twitter", hint: "5 Мбит · -14 LUFS" },
];

export function ExportDialog({ jobId, reelId, onClose }: Props) {
  const [selected, setSelected] = useState<string>("tiktok");
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const onExport = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.exportReel(jobId, reelId, selected);
      setDownloadUrl(resp.download_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="surface-card w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2
            id="export-dialog-title"
            className="display-serif text-[22px] leading-tight text-[color:var(--paper)]"
          >
            Экспорт рилса
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
          >
            ×
          </button>
        </div>
        <div className="divider my-4">пресеты</div>

        <div className="flex flex-col gap-2">
          {PRESETS.map((preset) => {
            const active = selected === preset.id;
            return (
              <label
                key={preset.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 text-[13px] transition-colors ${
                  active
                    ? "border-[color:var(--gold)] bg-[color:var(--ink-2)]"
                    : "border-[color:var(--line)] bg-transparent hover:border-[color:var(--mute)]"
                }`}
              >
                <input
                  type="radio"
                  name="export-preset"
                  value={preset.id}
                  checked={active}
                  onChange={() => setSelected(preset.id)}
                  className="accent-[color:var(--gold)]"
                />
                <div className="flex flex-1 flex-col">
                  <span className="text-[color:var(--paper)]">
                    {preset.label}
                  </span>
                  <span className="mono text-[10px] uppercase tracking-[0.1em] text-[color:var(--mute-2)]">
                    {preset.hint}
                  </span>
                </div>
              </label>
            );
          })}
        </div>

        {error && (
          <p className="mt-3 text-[11px] text-[color:var(--danger)]">{error}</p>
        )}

        {downloadUrl && (
          <a
            href={downloadUrl}
            download
            className="btn btn-primary mt-4 w-full justify-center"
          >
            Скачать файл
          </a>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={loading}
            className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Готовлю..." : "Подготовить"}
          </button>
        </div>

        <p className="mt-3 text-[11px] leading-snug text-[color:var(--mute-2)]">
          MVP: возвращает ссылку на существующий MP4 с метаданными пресета.
          Full transcode по bitrate — в следующей итерации.
        </p>
      </div>
    </div>
  );
}
