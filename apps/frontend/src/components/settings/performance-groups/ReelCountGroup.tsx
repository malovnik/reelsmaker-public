
import { Group, SliderRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function ReelCountGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Количество и уникальность рилсов">
      <SwitchRow
        id="reel_count_enforce_floor_ceiling"
        label="Держать целевое количество по длительности"
        hint="10-15 мин → 10-15 рилсов; 15-30 мин → 12-20; 30-60 мин → 15-25; 60+ мин → 20-30. Стандарт: включено."
        checked={values.reel_count_enforce_floor_ceiling}
        onChange={(v) => update("reel_count_enforce_floor_ceiling", v)}
      />
      {values.reel_count_enforce_floor_ceiling && (
        <SliderRow
          id="reel_count_dedup_jaccard_threshold"
          label="Порог уникальности между рилсами"
          hint="0,7 = допустимо 70% пересечения слов — хорошая целевая уникальность. Меньше — жёстче отсев дублей, но рилсов будет меньше. Стандарт: 0,7."
          value={values.reel_count_dedup_jaccard_threshold}
          min={0.4}
          max={0.95}
          step={0.05}
          onChange={(v) => update("reel_count_dedup_jaccard_threshold", v)}
        />
      )}
      <button
        type="button"
        onClick={onReset}
        className="self-start text-xs text-[color:var(--accent-primary)] underline-offset-2 hover:underline"
      >
        Вернуть стандартные значения
      </button>
    </Group>
  );
}
