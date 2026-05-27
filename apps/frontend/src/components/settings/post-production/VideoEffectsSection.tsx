
import type { PostProductionConfig } from "@/lib/api";
import { Section, Toggle } from "./shared";

interface Props {
  config: PostProductionConfig;
  onConfigChange: <K extends keyof PostProductionConfig>(
    key: K,
    value: PostProductionConfig[K],
  ) => void;
}

export function VideoEffectsSection({ config, onConfigChange }: Props) {
  return (
    <Section title="Видео-эффекты">
      <Toggle
        label="Чёрно-белый кинематографичный фильтр"
        checked={config.bw_enabled}
        onChange={(v) => onConfigChange("bw_enabled", v)}
      />
      <p className="text-[11px] text-[color:var(--mute)]">
        Полное обесцвечивание с сохранением мягких тональных
        переходов — без полос и артефактов.
      </p>
    </Section>
  );
}
