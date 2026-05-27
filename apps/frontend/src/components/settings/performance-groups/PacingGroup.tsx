
import { Group, SelectRow, SliderRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function PacingGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Темп и ритм (pacing + snap)">
      <SelectRow<"dynamic" | "balanced" | "mkbhd_clean" | "documentary">
        id="pacing_profile"
        label="Темп монтажа"
        hint="Dynamic — быстрые склейки 1,5–3,5 с для энергичной речи. Balanced — 2,5–5 с под обычный разговор. MKBHD Clean — 3–6 с с воздухом. Documentary — 4–8 с для спокойного повествования. Стандарт: Balanced."
        value={values.pacing_profile}
        options={[
          { value: "dynamic", label: "Dynamic — быстрый" },
          { value: "balanced", label: "Balanced — сбалансированный (стандарт)" },
          { value: "mkbhd_clean", label: "MKBHD Clean — с воздухом" },
          { value: "documentary", label: "Documentary — медленный" },
        ]}
        onChange={(v) => update("pacing_profile", v)}
      />
      <SelectRow<"off" | "beat" | "onset" | "both">
        id="snap_strategy"
        label="Привязка склеек"
        hint="Onset — к фонетическим пикам речи (talking head, стандарт). Beat — к ударам музыки (для видео с саундтреком). Both — onset + fallback на beat. Off — без привязки."
        value={values.snap_strategy}
        options={[
          { value: "onset", label: "Onset — к слогам речи (стандарт)" },
          { value: "beat", label: "Beat — к музыкальным битам" },
          { value: "both", label: "Both — onset + beat fallback" },
          { value: "off", label: "Off — без привязки" },
        ]}
        onChange={(v) => update("snap_strategy", v)}
      />
      {values.snap_strategy !== "off" && (
        <SliderRow
          id="onset_snap_max_shift_sec"
          label="Максимальный сдвиг склейки"
          hint="Насколько далеко склейка может сдвинуться чтобы попасть на onset. Больше — чище склейки, но смещает тайминг. Стандарт: 0,08 с."
          value={values.onset_snap_max_shift_sec}
          min={0.02}
          max={0.2}
          step={0.01}
          onChange={(v) => update("onset_snap_max_shift_sec", v)}
        />
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
