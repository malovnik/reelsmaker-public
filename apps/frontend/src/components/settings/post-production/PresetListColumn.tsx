
import type { PostProductionPreset } from "@/lib/api";

interface Props {
  presets: PostProductionPreset[];
  selectedPresetId: number | "new" | null;
  onSelect: (id: number | "new" | null) => void;
}

export function PresetListColumn({
  presets,
  selectedPresetId,
  onSelect,
}: Props) {
  return (
    <section className="surface-card flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
          Пресеты
        </h2>
        <button
          onClick={() => onSelect("new")}
          type="button"
          className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--accent-primary)] hover:text-[color:var(--accent-primary)]"
        >
          + новый
        </button>
      </div>
      <div className="flex max-h-[70vh] flex-col gap-1 overflow-y-auto">
        {presets.length === 0 && (
          <p className="text-[11px] text-[color:var(--text-muted)]">
            Пресетов пока нет — жми «+ новый», и через минуту будет первый.
          </p>
        )}
        {presets.map((p) => {
          const active = selectedPresetId === p.id;
          return (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              type="button"
              className={`flex flex-col gap-0.5 rounded-lg border p-2 text-left transition-colors ${
                active
                  ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary-subtle)]"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-default)]"
              }`}
            >
              <span
                className={`text-xs font-medium ${
                  active
                    ? "text-[color:var(--accent-primary-hover)]"
                    : "text-[color:var(--text-primary)]"
                }`}
              >
                {p.is_default ? "★ " : ""}
                {p.name}
              </span>
              <span className="font-mono text-[10px] text-[color:var(--text-muted)]">
                {p.config.zoom_enabled ? "зум" : "без зума"} ·{" "}
                {p.config.audio_normalize_enabled
                  ? `${p.config.audio_target_lufs} LUFS`
                  : "звук не нормализуется"}
              </span>
              {(p.intro_asset || p.outro_asset) && (
                <span className="font-mono text-[10px] text-[color:var(--text-disabled)]">
                  {p.intro_asset ? "интро" : ""}
                  {p.intro_asset && p.outro_asset ? " + " : ""}
                  {p.outro_asset ? "аутро" : ""}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
