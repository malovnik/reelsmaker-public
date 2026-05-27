
import { Group, SelectRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function CrossChunkGroup({ values, update }: GroupProps) {
  return (
    <Group title="Сверка кандидатов между частями (cross-chunk reducer)">
      <SwitchRow
        id="cross_chunk_reducer_enabled"
        label="Дополнительная проверка согласованности"
        hintKey="cross_chunk_reducer"
        checked={values.cross_chunk_reducer_enabled}
        onChange={(v) => update("cross_chunk_reducer_enabled", v)}
      />
      {values.cross_chunk_reducer_enabled && (
        <SelectRow
          id="cross_chunk_reducer_strictness"
          label="Строгость"
          hint="«Мягкая» — только явные противоречия (уверенность высокая). «Жёсткая» — любые расхождения, даже спорные. Жёсткая режет больше, но и случаев false positive больше."
          value={values.cross_chunk_reducer_strictness}
          options={[
            { value: "soft", label: "Мягкая" },
            { value: "strict", label: "Жёсткая" },
          ]}
          onChange={(v) =>
            update("cross_chunk_reducer_strictness", v as "soft" | "strict")
          }
        />
      )}
    </Group>
  );
}
