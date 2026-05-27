
import { Group, NumberRow } from "@/components/settings-shared";
import { COHERENCE_MODES, type CoherenceMode } from "@/lib/api";
import type { GroupProps } from "./types";

const COHERENCE_MODE_META: Record<
  CoherenceMode,
  { label: string; hint: string }
> = {
  off: {
    label: "Не проверять",
    hint: "Рилсы идут как есть — быстрее, но возможны рассогласованные склейки.",
  },
  reject: {
    label: "Убирать слабые",
    hint: "Рассогласованные рилсы выбрасываются. Итоговое количество может быть меньше запрошенного.",
  },
  resort: {
    label: "Пробовать заменить",
    hint: "Подбираем другой финал из той же темы. Если не получилось — оставляем как есть.",
  },
};

function CoherenceModeRow({
  value,
  onChange,
}: {
  value: CoherenceMode;
  onChange: (v: CoherenceMode) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col">
        <span className="text-sm text-[color:var(--text-primary)]">
          Что делать с рилсами, где hook и финал расходятся
        </span>
        <p className="mt-1 text-xs text-[color:var(--text-muted)]">
          После сборки каждый рилс проверяется на связность. Эта настройка
          решает, что делать с рассогласованными кандидатами.
        </p>
      </div>
      <div
        role="radiogroup"
        aria-label="Режим проверки связности"
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      >
        {COHERENCE_MODES.map((mode) => {
          const meta = COHERENCE_MODE_META[mode];
          const active = mode === value;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(mode)}
              className={`flex flex-col items-start gap-1 rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--accent-primary)] ${
                active
                  ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary-subtle)] text-[color:var(--accent-primary-hover)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
              }`}
            >
              <span className="text-sm font-medium">{meta.label}</span>
              <span
                className={`text-[11px] leading-snug ${
                  active
                    ? "text-[color:var(--accent-primary)]"
                    : "text-[color:var(--text-muted)]"
                }`}
              >
                {meta.hint}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ThresholdAdvice({
  value,
  mode,
}: {
  value: number;
  mode: CoherenceMode;
}) {
  const v = Math.round(value * 100) / 100;
  const severity: "warn" | "danger" | null =
    v > 0.8 ? "danger" : v > 0.7 ? "warn" : null;
  const recommendation =
    mode === "reject"
      ? "Для режима «убирать слабые» разумно 0,50–0,60. Выше 0,70 — отрежет большую часть рилсов."
      : "Для режима «пробовать заменить» разумно 0,65–0,75. Выше 0,80 — пересборка сработает редко.";

  return (
    <div className="flex flex-col gap-2" aria-live="polite">
      {severity === "warn" && (
        <div
          role="alert"
          className="rounded-lg border border-[color:var(--warning)] bg-[color:var(--warning)]/10 px-3 py-2 text-xs leading-snug text-[color:var(--warning)]"
        >
          Строгий порог — возможна потеря 30–50 % рилсов в режиме отбрасывания.
        </div>
      )}
      {severity === "danger" && (
        <div
          role="alert"
          className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 px-3 py-2 text-xs leading-snug text-[color:var(--danger)]"
        >
          Очень строгий порог — почти все рилсы могут быть отброшены.
        </div>
      )}
      <p className="text-[11px] leading-snug text-[color:var(--text-muted)]">
        {recommendation}
      </p>
    </div>
  );
}

export function CoherenceGroup({ values, update }: GroupProps) {
  return (
    <Group title="Связность рилсов">
      <CoherenceModeRow
        value={values.coherence_mode}
        onChange={(v) => update("coherence_mode", v)}
      />
      {values.coherence_mode !== "off" && (
        <>
          <NumberRow
            id="coherence_threshold"
            label="Порог связности"
            hint="Рилсы со связностью ниже этого значения считаются рассогласованными. Ниже 0,5 — считаются связными почти всегда, выше 0,8 — жёсткий фильтр."
            value={Math.round(values.coherence_threshold * 100) / 100}
            min={0.3}
            max={0.9}
            step={0.05}
            onChange={(v) => update("coherence_threshold", v)}
          />
          <ThresholdAdvice
            value={values.coherence_threshold}
            mode={values.coherence_mode}
          />
        </>
      )}
    </Group>
  );
}
