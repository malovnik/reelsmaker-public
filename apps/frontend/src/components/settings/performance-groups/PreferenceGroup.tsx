
import { Group, SelectRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function PreferenceGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Личные предпочтения (ML на лайках)">
      <SelectRow<"cosine" | "top_by_date">
        id="preference_retrieval_mode"
        label="Режим поиска похожих лайкнутых рилсов"
        hint="Cosine — семантический поиск через Gemini embeddings (требует хотя бы несколько лайков с эмбеддингами; старые лайки до T6.1 автоматически падают на резервный путь). Top-by-date — стандарт: топ-8 лайков по дате. Стандарт: cosine."
        value={values.preference_retrieval_mode}
        options={[
          { value: "cosine", label: "Cosine — семантический (стандарт)" },
          { value: "top_by_date", label: "По дате (legacy топ-8)" },
        ]}
        onChange={(v) => update("preference_retrieval_mode", v)}
      />
      <button
        type="button"
        onClick={onReset}
        className="self-start text-xs text-[color:var(--gold)] underline-offset-2 hover:underline"
      >
        Вернуть стандартные значения
      </button>
    </Group>
  );
}
