
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function EnsembleGroup({ values, update }: GroupProps) {
  return (
    <Group title="Ансамбль судей (точность ранжирования)">
      <NumberRow
        id="reducer_ensemble_size"
        label="Сколько судей голосует за рилс"
        hintKey="reducer_ensemble"
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
