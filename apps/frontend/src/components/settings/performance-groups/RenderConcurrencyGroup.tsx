
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function RenderConcurrencyGroup({ values, update }: GroupProps) {
  return (
    <Group title="Параллельный рендер">
      <NumberRow
        id="render_concurrency"
        label="Сколько рилсов рендерим одновременно"
        hint="На обычном MacBook оптимум 2–3. Больше — быстрее, но нагружает процессор."
        value={values.render_concurrency}
        min={1}
        max={8}
        step={1}
        onChange={(v) => update("render_concurrency", v)}
      />
    </Group>
  );
}
