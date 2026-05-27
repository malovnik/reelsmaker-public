
import { Group, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function DefaultsGroup({ values, update }: GroupProps) {
  return (
    <Group title="По умолчанию для новых нарезок">
      <SwitchRow
        id="default_use_source_for_render"
        label="Рендерить из исходного видео"
        hint="Финальный рендер использует оригинал, а не облегчённую копию. Дольше, но максимальное качество."
        checked={values.default_use_source_for_render}
        onChange={(v) => update("default_use_source_for_render", v)}
      />
    </Group>
  );
}
