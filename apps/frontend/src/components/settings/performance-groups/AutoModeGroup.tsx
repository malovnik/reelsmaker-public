
import { Group, SelectRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function AutoModeGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Автоматический режим (робот-монтажёр)">
      <SelectRow<"automatic" | "manual">
        id="pipeline_mode"
        label="Режим обработки"
        hint="Автоматический — advisor анализирует аудио и сам выбирает склейки, звук, движение. Ручной — pipeline использует твои настройки без попыток изменить их. Стандарт: Автоматический."
        value={values.pipeline_mode}
        options={[
          { value: "automatic", label: "Автоматический (рекомендуется)" },
          { value: "manual", label: "Ручной" },
        ]}
        onChange={(v) => update("pipeline_mode", v)}
      />
      <p className="text-xs text-[color:var(--mute)]">
        Формат кадра, модель распознавания, включатели зума и ч-б —
        Auto не трогает, они остаются под твоим контролем в UploadWizard.
      </p>
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
