
import { Group, SelectRow, SliderRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

/**
 * Fix 5 — «Качество и длительность рилсов».
 *
 * Управляет дорогими стадиями pipeline, которые юзер может отключить ради
 * скорости/экспериментов, а также целевой длительностью рилса и силой
 * подтягивания к ней (reel_target_duration_sec / reel_target_pull_strength
 * дублируют env-defaults из core.config.Settings через UI override).
 *
 * По умолчанию — эталонное поведение (variants on, critique on, resort,
 * 50s soft). Изменять стоит только если чётко понимаешь компромисс.
 */
export function QualityGatesGroup({ values, update }: GroupProps) {
  return (
    <Group title="Качество и длительность рилсов">
      <SliderRow
        id="reel_target_duration_sec"
        label="Целевая длительность рилса (сек)"
        hint="37 — минимум платформ, 50 — эталон с emotional buildup, 55+ — для сложных тезисов. Композер тянет к target только слабые арки."
        value={values.reel_target_duration_sec}
        min={37}
        max={75}
        step={1}
        onChange={(v) => update("reel_target_duration_sec", v)}
      />
      <SelectRow
        id="reel_target_pull_strength"
        label="Сила подтягивания к целевой длительности"
        hint="soft — рекомендованный default: тянет только тонкие арки (< 2 development-сегментов). off — не трогать. hard — все арки к target (legacy до 3c139c4)."
        value={values.reel_target_pull_strength}
        options={[
          { value: "off", label: "Off — не трогать арки" },
          { value: "soft", label: "Soft — только тонкие арки (<2 development)" },
          { value: "hard", label: "Hard — все арки к target" },
        ]}
        onChange={(v) => update("reel_target_pull_strength", v)}
      />
      <SwitchRow
        id="skip_complete_short_arcs"
        label="Защищать короткие punchy арки"
        hint="Вкл (default): короткие закрытые арки hook+payoff под REEL_MIN живут как отдельные рилсы 30-40s. Выкл: сливаются с соседями для более длинных рилсов 45-80s с большим emotional buildup."
        checked={values.skip_complete_short_arcs}
        onChange={(v) => update("skip_complete_short_arcs", v)}
      />
      <SwitchRow
        id="variants_generator_enabled"
        label="Генератор форматов (Stage 5.7)"
        hint="4 варианта рилса через Gemini Pro (long/package/punchy/deep). Выключение ускоряет pipeline ~15-20%, composer идёт по single long_philosophical копии."
        checked={values.variants_generator_enabled}
        onChange={(v) => update("variants_generator_enabled", v)}
      />
      <SwitchRow
        id="rhythm_critique_loop_enabled"
        label="Цикл ритмической критики (Stage 5.5)"
        hint="LLM переписывает арку до 3 раз для улучшения ритма. Выключение даёт больше вариабельности — Story Doctor работает в один проход."
        checked={values.rhythm_critique_loop_enabled}
        onChange={(v) => update("rhythm_critique_loop_enabled", v)}
      />
    </Group>
  );
}
