
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function FillerRemovalGroup({ values, update }: GroupProps) {
  return (
    <Group title="Удаление слов-паразитов">
      <SwitchRow
        id="filler_removal_enabled"
        label="Вырезать «эм», «ну», «вот», «типа», «um», «uh»"
        hintKey="filler_removal"
        checked={values.filler_removal_enabled}
        onChange={(v) => update("filler_removal_enabled", v)}
      />
      {values.filler_removal_enabled && (
        <>
          <SwitchRow
            id="filler_removal_aggressive"
            label="Агрессивный режим — также убирать невнятные слова"
            hint="Если уверенность STT ниже порога — считаем слово невнятным и режем. Помогает на быстрой речи, но может задеть легитимные слова."
            checked={values.filler_removal_aggressive}
            onChange={(v) => update("filler_removal_aggressive", v)}
          />
          {values.filler_removal_aggressive && (
            <NumberRow
              id="filler_confidence_threshold"
              label="Порог уверенности для агрессивного режима"
              hint="Слова с confidence ниже этого значения считаются невнятными. По умолчанию 0,35."
              value={Math.round(values.filler_confidence_threshold * 100) / 100}
              min={0.1}
              max={0.6}
              step={0.05}
              onChange={(v) => update("filler_confidence_threshold", v)}
            />
          )}
          <NumberRow
            id="filler_edge_buffer_sec"
            label="Буфер вокруг слова (секунды)"
            hint="Срез начинается раньше и заканчивается позже границ слова на это время. По умолчанию 0,03 с — убирает шипящие/придыхания."
            value={Math.round(values.filler_edge_buffer_sec * 1000) / 1000}
            min={0}
            max={0.15}
            step={0.01}
            onChange={(v) => update("filler_edge_buffer_sec", v)}
          />
        </>
      )}
    </Group>
  );
}
