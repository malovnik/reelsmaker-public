
import { Group, SelectRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function LLMGroup({ values, update }: GroupProps) {
  return (
    <Group title="Модели ИИ (качество vs скорость)">
      <SelectRow
        id="pipeline_llm_provider"
        label="Провайдер ИИ для нарезки"
        hintKey="llm_provider"
        value={values.pipeline_llm_provider}
        options={[
          { value: "gemini", label: "Gemini (по уровням моделей)" },
          { value: "zhipu", label: "Zhipu GLM-5.1 (весь конвейер на GLM)" },
        ]}
        onChange={(v) =>
          update("pipeline_llm_provider", v as "gemini" | "zhipu")
        }
      />
      <SelectRow
        id="llm_tier_profile"
        label="Режим качества моделей (только Gemini)"
        hintKey="llm_tier_profile"
        value={values.llm_tier_profile}
        options={[
          { value: "fast", label: "Качество — Pro / Flash / Flash-Lite по стадиям" },
          { value: "legacy", label: "Классика — Flash-Lite на всех стадиях (cheapest)" },
        ]}
        onChange={(v) => update("llm_tier_profile", v as "fast" | "legacy")}
      />
      {values.llm_tier_profile === "fast" && (
        <>
          <p className="rounded-none border border-l-2 border-[var(--line)] border-l-[var(--warning)] bg-[var(--ink)] p-3 text-[0.8125rem] leading-snug text-[var(--warning)]">
            Включает Gemini Pro на тяжёлых стадиях — это заметно дороже и
            медленнее. Для большинства видео «Классика» (Flash-Lite) даёт
            сопоставимый результат за копейки.
          </p>
          <SelectRow
            id="llm_lite_variant"
            label="Базовая Flash-Lite на лёгких стадиях"
            hintKey="llm_lite_variant"
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
