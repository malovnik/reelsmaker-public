
import {
  Group,
  NumberRow,
  SelectRow,
  SwitchRow,
} from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function JLCutGroup({ values, update }: GroupProps) {
  return (
    <Group title="Плавные переходы между сценами (J/L-cut)">
      <SwitchRow
        id="jl_cut_enabled"
        label="Включить плавные переходы"
        hint="L-cut: аудио текущей сцены ещё звучит поверх видео следующей. J-cut: аудио следующей начинается до переключения картинки. Сглаживает границы между кусками и делает рилс менее «резаным»."
        checked={values.jl_cut_enabled}
        onChange={(v) => update("jl_cut_enabled", v)}
      />
      {values.jl_cut_enabled && (
        <>
          <SelectRow
            id="jl_cut_mode"
            label="Где применять"
            hint="«Только на смене роли» — на переходах hook→развитие, развитие→пик, пик→финал. Звучит естественно, не перебивает монолог. «На всех границах» — между любыми соседними кусками, сильнее сглаживает, но может размывать акценты."
            value={values.jl_cut_mode}
            options={[
              { value: "role_change", label: "Только на смене роли" },
              { value: "all_transitions", label: "На всех границах" },
            ]}
            onChange={(v) =>
              update("jl_cut_mode", v as "role_change" | "all_transitions")
            }
          />
          <NumberRow
            id="jl_cut_max_offset_sec"
            label="Максимальная длина перехлёста (секунды)"
            hint="Насколько долго аудио тянется через границу. 0,3–0,5 с — стандартная киношная практика. Больше — риск каши, меньше — эффект едва заметен."
            value={Math.round(values.jl_cut_max_offset_sec * 100) / 100}
            min={0.1}
            max={1.0}
            step={0.05}
            onChange={(v) => update("jl_cut_max_offset_sec", v)}
          />
        </>
      )}
    </Group>
  );
}
