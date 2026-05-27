
import { useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/contexts";
import { Modal, Button } from "@/components/ui";

interface Props {
  jobId: string;
  reelId: string;
  onClose: () => void;
}

interface PresetOption {
  id: string;
  label: string;
  /** Что пресет реально задаёт: имя файла и шаблон подписи под площадку. */
  hint: string;
}

const PRESETS: PresetOption[] = [
  { id: "tiktok", label: "TikTok", hint: "Имя файла и подпись под TikTok" },
  { id: "reels", label: "Instagram Reels", hint: "Имя файла и подпись под Reels" },
  { id: "shorts", label: "YouTube Shorts", hint: "Имя файла и подпись под Shorts" },
  { id: "x", label: "X / Twitter", hint: "Имя файла и подпись под X" },
];

export function ExportDialog({ jobId, reelId, onClose }: Props) {
  const toast = useToast();
  const [selected, setSelected] = useState<string>("tiktok");
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const onExport = async () => {
    setLoading(true);
    try {
      const resp = await api.exportReel(jobId, reelId, selected);
      setDownloadUrl(resp.download_url);
    } catch (err) {
      toast.showError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Экспорт рилса"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={onExport} loading={loading}>
            {loading ? "Готовим" : "Подготовить файл"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.14em] text-[color:var(--copper)]">
            Площадка
          </legend>
          {PRESETS.map((preset) => {
            const active = selected === preset.id;
            return (
              <label
                key={preset.id}
                className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-none border px-3 py-2 text-[0.875rem] transition-colors ${
                  active
                    ? "border-[color:var(--gold)] bg-[color:var(--ink-3)]"
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
                  <span className="text-[color:var(--paper)]">{preset.label}</span>
                  <span className="text-[0.75rem] text-[color:var(--mute-2)]">
                    {preset.hint}
                  </span>
                </div>
              </label>
            );
          })}
        </fieldset>

        {downloadUrl && (
          <a
            href={downloadUrl}
            download
            className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-none border border-[color:var(--gold)] bg-[color:var(--gold)] text-[0.875rem] font-medium text-[color:var(--ink)] transition-colors hover:bg-[color:var(--accent-bright)]"
          >
            Скачать файл
          </a>
        )}

        <p className="text-[0.75rem] leading-relaxed text-[color:var(--mute-2)]">
          Отдаём готовый MP4 как есть — вертикаль 9:16, исходное качество.
          Пресет задаёт только имя файла и шаблон подписи. Пере-кодирование
          под площадку (битрейт, громкость) — в планах.
        </p>
      </div>
    </Modal>
  );
}
