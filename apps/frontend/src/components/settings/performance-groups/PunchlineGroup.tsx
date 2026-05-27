
import { Group, SliderRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function PunchlineGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Акценты (punchline pause)">
      <SwitchRow
        id="punchline_pause_enabled"
        label="Сохранять паузы после пунчлайнов"
        hint="Детектор ловит падение высоты голоса в конце фразы (признак punchline) и защищает паузу после него от сжатия. Даёт слушателю воздух после тезиса — как у ручного монтажа. Стандарт: включено."
        checked={values.punchline_pause_enabled}
        onChange={(v) => update("punchline_pause_enabled", v)}
      />
      {values.punchline_pause_enabled && (
        <>
          <SliderRow
            id="punchline_pitch_drop_hz"
            label="Порог падения высоты (Hz)"
            hint="Насколько резко должна упасть высота чтобы сработал punchline-детектор. Меньше — чаще срабатывает (больше пауз), больше — только явные акценты. Стандарт: 20 Hz."
            value={values.punchline_pitch_drop_hz}
            min={10}
            max={80}
            step={2}
            onChange={(v) => update("punchline_pitch_drop_hz", v)}
          />
          <SliderRow
            id="punchline_hold_after_sec"
            label="Длительность паузы после punchline"
            hint="Сколько секунд сохраняется тишина после тезиса. Стандарт: 0,5 с — комфортно слышится как заключительная пауза."
            value={values.punchline_hold_after_sec}
            min={0.2}
            max={1.5}
            step={0.05}
            onChange={(v) => update("punchline_hold_after_sec", v)}
          />
        </>
      )}
      <button
        type="button"
        onClick={onReset}
        className="self-start text-xs text-[color:var(--accent-primary)] underline-offset-2 hover:underline"
      >
        Вернуть стандартные значения
      </button>
    </Group>
  );
}
