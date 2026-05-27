
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function CutSnapGroup({ values, update }: GroupProps) {
  return (
    <Group title="Чистые срезы речи (word-aware snap)">
      <SwitchRow
        id="cut_snap_enabled"
        label="Прилеплять границы к началам/концам слов"
        hint="Если срез попал в середину слова — сдвигаем на 10-30 мс к ближайшему word boundary из точной разметки stable-ts. Убирает щелчки и обрывки согласных."
        checked={values.cut_snap_enabled}
        onChange={(v) => update("cut_snap_enabled", v)}
      />
      {values.cut_snap_enabled && (
        <NumberRow
          id="cut_snap_window_sec"
          label="Окно поиска (секунды)"
          hint="Максимальный сдвиг границы в любую сторону. 0,03 с (30 мс) — стандарт, почти незаметно на слух. Больше = сильнее сдвиг, риск затронуть важные миллисекунды."
          value={Math.round(values.cut_snap_window_sec * 1000) / 1000}
          min={0.01}
          max={0.1}
          step={0.005}
          onChange={(v) => update("cut_snap_window_sec", v)}
        />
      )}
    </Group>
  );
}
