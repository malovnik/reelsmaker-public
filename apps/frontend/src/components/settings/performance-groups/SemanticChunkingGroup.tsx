
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function SemanticChunkingGroup({ values, update }: GroupProps) {
  return (
    <Group title="Смысловая нарезка на части (semantic chunking)">
      <SwitchRow
        id="semantic_chunking_enabled"
        label="Резать видео по смысловым границам, а не по таймкодам"
        hint="Эмбеддинги предложений помогают разделить видео на части там, где автор меняет тему. Даёт +8–12% к качеству границ по сравнению с фиксированными окнами (Chapter-Llama, CVPR 2025). Если модель эмбеддингов недоступна — откат к таймкодам."
        checked={values.semantic_chunking_enabled}
        onChange={(v) => update("semantic_chunking_enabled", v)}
      />
      {values.semantic_chunking_enabled && (
        <>
          <NumberRow
            id="semantic_chunk_target_duration_sec"
            label="Целевая длина части (секунды)"
            hint="Средняя длина одной смысловой части. По умолчанию 600 с (10 мин)."
            value={values.semantic_chunk_target_duration_sec}
            min={120}
            max={1800}
            step={30}
            onChange={(v) =>
              update("semantic_chunk_target_duration_sec", v)
            }
          />
          <NumberRow
            id="semantic_chunk_min_duration_sec"
            label="Минимальная длина части (секунды)"
            hint="Алгоритм не делает части короче этого значения — защита от микро-фрагментов, из которых потом ничего не склеить."
            value={values.semantic_chunk_min_duration_sec}
            min={60}
            max={900}
            step={30}
            onChange={(v) => update("semantic_chunk_min_duration_sec", v)}
          />
          <NumberRow
            id="semantic_chunk_similarity_threshold"
            label="Порог смены темы"
            hint="Насколько сильно должна падать смысловая близость между соседними предложениями, чтобы здесь разделили части. 0,35 — средне, 0,2 — очень много границ, 0,5 — редкие границы."
            value={
              Math.round(values.semantic_chunk_similarity_threshold * 100) /
              100
            }
            min={0.05}
            max={0.8}
            step={0.05}
            onChange={(v) =>
              update("semantic_chunk_similarity_threshold", v)
            }
          />
        </>
      )}
    </Group>
  );
}
