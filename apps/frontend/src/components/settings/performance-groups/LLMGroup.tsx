
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
        hint="Качество — каждая стадия идёт на свою модель по уровню: тяжёлые планирующие стадии на Gemini Pro, средние на Flash, остальное на выбранной ниже Flash-Lite. Дороже и медленнее, но сильнее держит контекст длинных видео. Классика — одна модель 3.1 Flash Lite Preview на всех стадиях (cheapest, как было раньше). Игнорируется когда выбран Zhipu GLM-5.1."
        value={values.llm_tier_profile}
        options={[
          { value: "fast", label: "Качество — Pro / Flash / Flash-Lite по стадиям" },
          { value: "legacy", label: "Классика — Flash-Lite на всех стадиях (cheapest)" },
        ]}
        onChange={(v) => update("llm_tier_profile", v as "fast" | "legacy")}
      />
      {values.llm_tier_profile === "fast" && (
        <>
          <p className="rounded-lg border border-[color:var(--warning)]/30 bg-[color:var(--warning)]/10 p-3 text-xs leading-relaxed text-[color:var(--warning)]">
            Включает Gemini Pro на тяжёлых стадиях — это заметно дороже и
            медленнее обычного. Используй осознанно: для большинства видео
            «Классика» (Flash-Lite) даёт сопоставимый результат за копейки.
          </p>
          <SelectRow
            id="llm_lite_variant"
            label="Какой Flash-Lite использовать на лёгких стадиях"
            hint="3.1 Flash Lite Preview — дешевле, но preview-статус (возможны нестыковки JSON schema). 2.5 Flash Lite — стабильное production-поколение, лучше держит строгий schema, чуть дороже. Это базовая (дефолтная) модель — Pro/Flash подключаются только на стадиях, где они реально нужны."
            value={values.llm_lite_variant}
            options={[
              { value: "3_1", label: "Gemini 3.1 Flash Lite Preview" },
              { value: "2_5", label: "Gemini 2.5 Flash Lite (стабильная)" },
            ]}
            onChange={(v) => update("llm_lite_variant", v as "2_5" | "3_1")}
          />
        </>
      )}
    </Group>
  );
}
