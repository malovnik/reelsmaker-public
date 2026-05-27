
import type { PostProductionConfig } from "@/lib/api";
import { Field, Section, Toggle } from "./shared";

interface Props {
  config: PostProductionConfig;
  onConfigChange: <K extends keyof PostProductionConfig>(
    key: K,
    value: PostProductionConfig[K],
  ) => void;
}

export function AudioNormalizationSection({ config, onConfigChange }: Props) {
  return (
    <Section title="Громкость звука">
      <Toggle
        label="Нормализовать громкость"
        checked={config.audio_normalize_enabled}
        onChange={(v) => onConfigChange("audio_normalize_enabled", v)}
      />
      <Field label={`Целевая громкость: ${config.audio_target_lufs} LUFS`}>
        <input
          type="range"
          min="-30"
          max="-5"
          step="0.5"
          value={config.audio_target_lufs}
          disabled={!config.audio_normalize_enabled}
          onChange={(e) =>
            onConfigChange("audio_target_lufs", Number(e.target.value))
          }
          className="w-full accent-[color:var(--gold)]"
        />
        <span className="text-[11px] text-[color:var(--mute)]">
          Для Instagram, TikTok и YouTube стандарт — −14 LUFS.
          Для подкастов — −16 LUFS.
        </span>
      </Field>
    </Section>
  );
}
