
import type { PostProductionConfig } from "@/lib/api";
import { NumberField, Section, Toggle } from "./shared";

interface Props {
  config: PostProductionConfig;
  onConfigChange: <K extends keyof PostProductionConfig>(
    key: K,
    value: PostProductionConfig[K],
  ) => void;
}

export function ZoomSection({ config, onConfigChange }: Props) {
  return (
    <Section title="Зум с отслеживанием лица">
      <Toggle
        label="Включить зум"
        checked={config.zoom_enabled}
        onChange={(v) => onConfigChange("zoom_enabled", v)}
      />
      {config.zoom_enabled && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <NumberField
              label="Крупный план, %"
              value={config.zoom_close_percent}
              min={0}
              max={80}
              onChange={(v) => onConfigChange("zoom_close_percent", v)}
            />
            <NumberField
              label="Средний план, %"
              value={config.zoom_medium_percent}
              min={0}
              max={80}
              onChange={(v) => onConfigChange("zoom_medium_percent", v)}
            />
            <NumberField
              label="Дальний план, %"
              value={config.zoom_wide_percent}
              min={0}
              max={80}
              onChange={(v) => onConfigChange("zoom_wide_percent", v)}
            />
          </div>
          <Toggle
            label="Чередовать крупный, средний и дальний планы"
            checked={config.zoom_alternating_planes_enabled}
            onChange={(v) =>
              onConfigChange("zoom_alternating_planes_enabled", v)
            }
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <NumberField
              label="Применять эффект через каждый N-й переход"
              value={config.zoom_apply_every_nth_cut}
              min={1}
              max={20}
              onChange={(v) => onConfigChange("zoom_apply_every_nth_cut", v)}
            />
            <NumberField
              label="Не чаще, чем раз в (сек)"
              value={config.zoom_min_interval_sec}
              min={0}
              max={60}
              step={0.5}
              onChange={(v) => onConfigChange("zoom_min_interval_sec", v)}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <NumberField
              label="Длинный сегмент — больше (сек)"
              value={config.zoom_long_segment_threshold_sec}
              min={2}
              max={30}
              step={0.5}
              onChange={(v) =>
                onConfigChange("zoom_long_segment_threshold_sec", v)
              }
            />
            <NumberField
              label="Минимум под-плана (сек)"
              value={config.zoom_subsegment_min_sec}
              min={1}
              max={30}
              step={0.5}
              onChange={(v) => onConfigChange("zoom_subsegment_min_sec", v)}
            />
            <NumberField
              label="Максимум под-плана (сек)"
              value={config.zoom_subsegment_max_sec}
              min={1}
              max={30}
              step={0.5}
              onChange={(v) => onConfigChange("zoom_subsegment_max_sec", v)}
            />
          </div>
          <p className="text-[11px] text-[color:var(--text-muted)]">
            Длинные сегменты разбиваются на планы случайной длины.
            Камера смотрит в лицо, центр — по глазам.
          </p>
        </>
      )}
    </Section>
  );
}
