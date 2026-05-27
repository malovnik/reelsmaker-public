
import { Group, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function AdaptiveAudioGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Адаптивный звук (T8)">
      {/* DORMANT: mouth_sound_removal implementation deferred — detector
          runs but ProjectGraph is frozen, нет mute_zones API для внедрения
          результатов в финальный рендер. UI скрыт, чтобы не давать ложный
          контроль. Backend stub сохранён для будущей реализации. */}
      <SwitchRow
        id="breath_classifier_enabled"
        label="Отличать вдох от тишины"
        hint="Silero VAD не различает вдох и пустоту. Этот детектор помечает breath-зоны как «речь» и они не сжимаются. Стандарт: выключено."
        checked={values.breath_classifier_enabled}
        onChange={(v) => update("breath_classifier_enabled", v)}
      />
      <SwitchRow
        id="context_aware_keep_sec_enabled"
        label="Длительность паузы под пунктуацию"
        hint="Точка → 0,25 с, вопрос → 0,35 с, запятая → 0,12 с. Иначе глобальный keep_sec. Стандарт: включено."
        checked={values.context_aware_keep_sec_enabled}
        onChange={(v) => update("context_aware_keep_sec_enabled", v)}
      />
      <SwitchRow
        id="smart_jl_chooser_enabled"
        label="Контекстный выбор J/L-cut"
        hint="Planner берёт тип перехода и offset из контекста: вопрос → L-cut 0,25 с, смена говорящего → J-cut 0,30 с, тематический маркер → J-cut 0,35 с, эмоциональный пик → L-cut 0,30 с. Иначе фиксированный режим. Стандарт: выключено."
        checked={values.smart_jl_chooser_enabled}
        onChange={(v) => update("smart_jl_chooser_enabled", v)}
      />
      <SwitchRow
        id="adaptive_leveller_enabled"
        label="Адаптивное выравнивание громкости"
        hint="pyloudnorm меряет LUFS в окнах по 3 сек и локально поднимает тихие участки, приглушая громкие. Ровная громкость ±1 LU по всей длине рилса вместо глобального loudnorm. Стандарт: выключено."
        checked={values.adaptive_leveller_enabled}
        onChange={(v) => update("adaptive_leveller_enabled", v)}
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
