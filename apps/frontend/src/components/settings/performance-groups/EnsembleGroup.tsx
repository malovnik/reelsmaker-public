
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function EnsembleGroup({ values, update }: GroupProps) {
  return (
    <Group title="Ансамбль судей (точность ранжирования)">
      <NumberRow
        id="reducer_ensemble_size"
        label="Сколько судей голосует за рил"
        hint="1 — обычный режим, один LLM-вызов. 3-5 — параллельные вызовы с разной температурой, медиана-оценка + вето (рил попадает только если за него хотя бы N голосов). Стоимость растёт в N раз, точность по Q4/RewardBench 2 выше на 7-10 процентных пунктов."
        value={values.reducer_ensemble_size}
        min={1}
        max={5}
        step={1}
        onChange={(v) => update("reducer_ensemble_size", v)}
      />
      {values.reducer_ensemble_size > 1 && (
        <NumberRow
          id="reducer_ensemble_veto"
          label="Минимум голосов за рил"
          hint="Рил попадает в итог только если за него проголосовало не меньше этого числа судей. Защищает от случайных fluke-голосов одного судьи."
          value={values.reducer_ensemble_veto}
          min={1}
          max={values.reducer_ensemble_size}
          step={1}
          onChange={(v) => update("reducer_ensemble_veto", v)}
        />
      )}
    </Group>
  );
}
