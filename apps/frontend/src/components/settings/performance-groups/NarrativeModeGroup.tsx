
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

type NarrativeMode = "bottom_up" | "map_reduce" | "viral_2026";

const NARRATIVE_MODE_META: Record<
  NarrativeMode,
  { label: string; hint: string }
> = {
  bottom_up: {
    label: "Bottom-up (legacy)",
    hint: "Классический 9-стадийный pipeline: 6 extraction-агентов → reducer → story_doctor → composer с padding до MIN. Стабильный, дорогой, узкое распределение длин рилсов.",
  },
  map_reduce: {
    label: "Map-Reduce (Phase 8, OpusClip-parity)",
    hint: "Транскрипт → chunks по 20K chars → parallel LLM scoring → LLM reducer. Density 1 рилс на ~2 минуты. Работает на монологах, лекциях, подкастах, интервью.",
  },
  viral_2026: {
    label: "Viral 2026 (самый быстрый, OpusClip-style)",
    hint: "Один LLM call per chunk 20K знаков эмиттит готовые рилсы по 5-block структуре (Hook → Context → Payoff → Re-hook → CTA) и манифесту Живого Кадра. Multi-segment с flash-forward hooks. ~10-15 LLM вызовов на 90 мин видео вместо 80-120. Production target для talking-head.",
  },
};

export function NarrativeModeGroup({ values, update }: GroupProps) {
  // `chaptered` снят с поддержки (нет рабочего call-site) — стейт из старой БД
  // коерсим к bottom_up, чтобы радиогруппа не оставалась без выбора.
  const raw = values.narrative_mode ?? "bottom_up";
  const current = (raw === "chaptered" ? "bottom_up" : raw) as NarrativeMode;

  return (
    <Group title="Архитектура сборки рилсов" hintKey="narrative_mode">
      {raw === "chaptered" && (
        <p className="rounded-none border border-l-2 border-[var(--line)] border-l-[var(--danger)] bg-[var(--ink)] px-3 py-2 text-[0.8125rem] leading-snug text-[var(--mute)]">
          Сохранённый режим «по главам» помечен как нерабочий и заменён на
          Bottom-up. Выберите рабочую архитектуру ниже.
        </p>
      )}
      <p className="text-[0.8125rem] leading-snug text-[var(--mute)]">
        Три архитектуры на выбор. Bottom-up по умолчанию не меняет существующий
        конвейер. Для плотной нарезки в стиле OpusClip берите Map-Reduce.
      </p>
      <div className="flex flex-col gap-3">
        {(Object.keys(NARRATIVE_MODE_META) as NarrativeMode[]).map((mode) => {
          const meta = NARRATIVE_MODE_META[mode];
          const checked = current === mode;
          return (
            <label
              key={mode}
              className={`flex cursor-pointer flex-col gap-1 rounded-none border p-4 transition-colors ${
                checked
                  ? "border-[var(--gold)] bg-[var(--ink-3)]"
                  : "border-[var(--line)] bg-[var(--ink)] hover:border-[var(--mute)]"
              }`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="radio"
                  name="narrative_mode"
                  checked={checked}
                  onChange={() => update("narrative_mode", mode)}
                  className="h-4 w-4 accent-[var(--gold)]"
                />
                <span className="text-[0.9375rem] font-medium text-[var(--paper)]">
                  {meta.label}
                </span>
              </div>
              <p className="pl-7 text-[0.8125rem] leading-snug text-[var(--mute)]">
                {meta.hint}
              </p>
            </label>
          );
        })}
      </div>

      {current === "map_reduce" && (
        <div className="mt-4 flex flex-col gap-3 border-t border-[var(--line)] pt-4">
          <p className="text-[0.8125rem] leading-snug text-[var(--mute)]">
            Настройки конвейера Map-Reduce. Дефолты подобраны под talking-head —
            трогайте, только если видите проблемы.
          </p>
          <NumberRow
            id="narrative_chunk_size_chars"
            label="Размер куска (символов)"
            hintKey="narrative_chunk_size_chars"
            value={values.narrative_chunk_size_chars ?? 20000}
            onChange={(v) => update("narrative_chunk_size_chars", v)}
            min={5000}
            max={50000}
            step={1000}
          />
          <NumberRow
            id="narrative_chunk_overlap_chars"
            label="Перекрытие кусков (символов)"
            hintKey="narrative_chunk_overlap_chars"
            value={values.narrative_chunk_overlap_chars ?? 2000}
            onChange={(v) => update("narrative_chunk_overlap_chars", v)}
            min={500}
            max={5000}
            step={500}
          />
          <NumberRow
            id="narrative_clips_per_chunk_target"
            label="Моментов на кусок"
            hintKey="narrative_clips_per_chunk_target"
            value={values.narrative_clips_per_chunk_target ?? 15}
            onChange={(v) => update("narrative_clips_per_chunk_target", v)}
            min={5}
            max={30}
            step={1}
          />
          <NumberRow
            id="narrative_chunk_parallel_max"
            label="Кусков одновременно"
            hintKey="narrative_chunk_parallel_max"
            value={values.narrative_chunk_parallel_max ?? 10}
            onChange={(v) => update("narrative_chunk_parallel_max", v)}
            min={1}
            max={20}
            step={1}
          />
        </div>
      )}
    </Group>
  );
}
