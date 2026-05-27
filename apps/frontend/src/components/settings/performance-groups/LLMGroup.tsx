
import { Group, SelectRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function LLMGroup({ values, update }: GroupProps) {
  return (
    <Group title="Модели ИИ (качество vs скорость)">
      <SelectRow
        id="pipeline_llm_provider"
        label="LLM-провайдер для нарезки"
        hint="Gemini — основной провайдер с tier-матрицей (режим ниже). Zhipu GLM-5.1 — альтернатива: весь pipeline идёт через GLM-5.1 (требуется ZHIPU_API_KEY в .env). Hard switch: режим работы ниже игнорируется."
        value={values.pipeline_llm_provider}
        options={[
          { value: "gemini", label: "Gemini (tier-матрица)" },
          { value: "zhipu", label: "Zhipu GLM-5.1 (hard switch)" },
        ]}
        onChange={(v) =>
          update("pipeline_llm_provider", v as "gemini" | "zhipu")
        }
      />
      <SelectRow
        id="llm_tier_profile"
        label="Режим работы нейросети (только для Gemini)"
        hint="Быстро — выбранная ниже Lite-модель используется везде. Классика — одна-модель-везде 3.1 Flash Lite Preview как было раньше. Только Lite-варианты — более дорогие модели отключены. Игнорируется когда выбран Zhipu GLM-5.1."
        value={values.llm_tier_profile}
        options={[
          { value: "fast", label: "Быстро — Lite везде (cheapest)" },
          { value: "legacy", label: "Классика — 3.1 Flash Lite Preview везде" },
        ]}
        onChange={(v) => update("llm_tier_profile", v as "fast" | "legacy")}
      />
      {values.llm_tier_profile === "fast" && (
        <SelectRow
          id="llm_lite_variant"
          label="Какой Lite использовать"
          hint="3.1 Flash Lite Preview — дешевле, но preview-статус (возможны нестыковки JSON schema). 2.5 Flash Lite — стабильное production-поколение, лучше держит строгий schema, чуть дороже."
          value={values.llm_lite_variant}
          options={[
            { value: "3_1", label: "Gemini 3.1 Flash Lite Preview" },
            { value: "2_5", label: "Gemini 2.5 Flash Lite (стабильная)" },
          ]}
          onChange={(v) => update("llm_lite_variant", v as "2_5" | "3_1")}
        />
      )}
    </Group>
  );
}
