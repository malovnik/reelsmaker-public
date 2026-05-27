
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
    <Group title="Архитектура сборки рилсов">
      <p className="text-xs text-[color:var(--text-muted)]">
        Три архитектуры на выбор. Default bottom_up — не меняет существующий
        pipeline. Для тестов OpusClip-quality переключайся на map_reduce.
      </p>
      <div className="flex flex-col gap-3">
        {(Object.keys(NARRATIVE_MODE_META) as NarrativeMode[]).map((mode) => {
          const meta = NARRATIVE_MODE_META[mode];
          const checked = current === mode;
          return (
            <label
              key={mode}
              className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-4 transition-colors ${
                checked
                  ? "border-[color:var(--accent)] bg-[color:var(--surface-accent)]"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--surface)] hover:border-[color:var(--border)]"
              }`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="radio"
                  name="narrative_mode"
                  checked={checked}
                  onChange={() => update("narrative_mode", mode)}
                  className="h-4 w-4"
                />
                <span className="text-sm font-medium text-[color:var(--text-primary)]">
                  {meta.label}
                </span>
              </div>
              <p className="pl-7 text-xs text-[color:var(--text-muted)]">
                {meta.hint}
              </p>
            </label>
          );
        })}
      </div>

      {current === "map_reduce" && (
        <div className="mt-4 flex flex-col gap-3 border-t border-[color:var(--border-subtle)] pt-4">
          <p className="text-xs text-[color:var(--text-muted)]">
            Настройки Map-Reduce pipeline. Разумные дефолты из research
            OpusClip 2026 — тюнь только если видишь проблемы.
          </p>
          <NumberRow
            id="narrative_chunk_size_chars"
            label="Размер chunk'а (символов)"
            hint="20000 ≈ 20 минут talking-head речи. Меньше — теряется контекст арки, больше — Flash Lite context rot."
            value={values.narrative_chunk_size_chars ?? 20000}
            onChange={(v) => update("narrative_chunk_size_chars", v)}
            min={5000}
            max={50000}
            step={1000}
          />
          <NumberRow
            id="narrative_chunk_overlap_chars"
            label="Overlap между chunks (символов)"
            hint="Перекрытие для catch'а clips с hook/payoff на границе. Dedup по timestamps downstream."
            value={values.narrative_chunk_overlap_chars ?? 2000}
            onChange={(v) => update("narrative_chunk_overlap_chars", v)}
            min={500}
            max={5000}
            step={500}
          />
          <NumberRow
            id="narrative_clips_per_chunk_target"
            label="Density-prior (clips на chunk)"
            hint="Сколько clips LLM должен искать в одном 20K chunk'е. OpusClip observed 12-18. Floor, не cap."
            value={values.narrative_clips_per_chunk_target ?? 15}
            onChange={(v) => update("narrative_clips_per_chunk_target", v)}
            min={5}
            max={30}
            step={1}
          />
          <NumberRow
            id="narrative_chunk_parallel_max"
            label="Parallel LLM calls max"
            hint="Rate limit guard. Gemini Tier 1 = 300 RPM — 10 parallel × 3 videos/min fits."
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
