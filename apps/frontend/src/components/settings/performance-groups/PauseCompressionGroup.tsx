
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function PauseCompressionGroup({ values, update }: GroupProps) {
  return (
    <Group title="Сжатие пауз в речи">
      <SwitchRow
        id="pause_compression_enabled"
        label="Укорачивать длинные паузы"
        hint="Silero VAD находит паузы длиннее порога и сокращает их до целевой длительности. Рилс звучит плотнее, умещает больше смысла в 30-60 секунд."
        checked={values.pause_compression_enabled}
        onChange={(v) => update("pause_compression_enabled", v)}
      />
      {values.pause_compression_enabled && (
        <>
          <NumberRow
            id="pause_compression_threshold_sec"
            label="Порог — от какой длительности сжимаем"
            hint="Паузы короче этого значения не трогаем — они нужны для дыхания и пунктуации. По умолчанию 0,4 с."
            value={Math.round(values.pause_compression_threshold_sec * 100) / 100}
            min={0.2}
            max={2.0}
            step={0.1}
            onChange={(v) => update("pause_compression_threshold_sec", v)}
          />
          <NumberRow
            id="pause_compression_keep_sec"
            label="Сколько тишины оставить"
            hint="Длинная пауза обрезается до этой длительности. По умолчанию 0,2 с — слышно дыхание, речь остаётся естественной."
            value={Math.round(values.pause_compression_keep_sec * 100) / 100}
            min={0.05}
            max={1.0}
            step={0.05}
            onChange={(v) => update("pause_compression_keep_sec", v)}
          />
        </>
      )}
      {values.pause_compression_enabled && (
        <>
          <SwitchRow
            id="breath_compression_enabled"
            label="Дополнительно сжимать межфразовые вдохи"
            hint="Второй проход после сжатия пауз. Ловит короткие 0,2–0,4 с паузы — обычно это межфразовые вдохи — и ещё ужимает их. Речь становится максимально плотной. Может звучать скороговоркой если исходная речь уже быстрая."
            checked={values.breath_compression_enabled}
            onChange={(v) => update("breath_compression_enabled", v)}
          />
          {values.breath_compression_enabled && (
            <>
              <NumberRow
                id="breath_compression_threshold_sec"
                label="Минимальная длительность вдоха"
                hint="Паузы короче — не трогаем (это внутриречевые микропаузы). Выше 0,25 с — обычно вдох."
                value={Math.round(values.breath_compression_threshold_sec * 100) / 100}
                min={0.15}
                max={0.5}
                step={0.05}
                onChange={(v) => update("breath_compression_threshold_sec", v)}
              />
              <NumberRow
                id="breath_compression_keep_sec"
                label="Сколько оставить после сжатия"
                hint="Слишком мало — речь склеится без дыхания. 0,08 с — баланс между плотностью и естественностью."
                value={Math.round(values.breath_compression_keep_sec * 100) / 100}
                min={0.03}
                max={0.2}
                step={0.01}
                onChange={(v) => update("breath_compression_keep_sec", v)}
              />
            </>
          )}
        </>
      )}
    </Group>
  );
}
