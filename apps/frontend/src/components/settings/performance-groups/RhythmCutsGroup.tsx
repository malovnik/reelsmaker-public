
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function RhythmCutsGroup({ values, update }: GroupProps) {
  return (
    <Group title="Срезы под бит музыки (для видео с саундтреком)">
      <SwitchRow
        id="rhythm_aware_cuts_enabled"
        label="Прилеплять границы к бит-паттерну"
        hint="librosa детектирует биты в фоновой музыке и сдвигает каждый cut на ближайший ритмический удар. Полезно для fashion-показов и travel-видео с саундтреком. Для talking-head без музыки автоматически отключается (биты не находятся)."
        checked={values.rhythm_aware_cuts_enabled}
        onChange={(v) => update("rhythm_aware_cuts_enabled", v)}
      />
      {values.rhythm_aware_cuts_enabled && (
        <NumberRow
          id="rhythm_aware_max_shift_sec"
          label="Макс. сдвиг к биту (секунды)"
          hint="Не сдвигаем cut дальше этого значения. 0,15 с сохраняет слова целыми (±30 мс word-snap), но попадает в ритм."
          value={Math.round(values.rhythm_aware_max_shift_sec * 1000) / 1000}
          min={0.05}
          max={0.3}
          step={0.01}
          onChange={(v) => update("rhythm_aware_max_shift_sec", v)}
        />
      )}
    </Group>
  );
}
