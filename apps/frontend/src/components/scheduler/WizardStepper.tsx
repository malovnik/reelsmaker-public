import { cn } from "@/components/ui";

export type WizardStep = 1 | 2 | 3 | 4;

export const WIZARD_STEP_LABELS: Record<WizardStep, string> = {
  1: "Рилсы",
  2: "Аккаунты",
  3: "Расписание",
  4: "Подтверждение",
};

interface Props {
  current: WizardStep;
  /** Перейти на уже пройденный шаг. */
  onGoto: (step: WizardStep) => void;
}

/**
 * Индикатор шагов мастера кампании. Пройденные шаги кликабельны, текущий —
 * золотой, будущие приглушены. Тач-таргет ≥44px.
 */
export function WizardStepper({ current, onGoto }: Props) {
  return (
    <nav
      aria-label="Шаги создания кампании"
      className="grid grid-cols-2 gap-2 sm:grid-cols-4"
    >
      {([1, 2, 3, 4] as WizardStep[]).map((n) => {
        const active = n === current;
        const done = n < current;
        const clickable = done;
        return (
          <button
            key={n}
            type="button"
            onClick={() => clickable && onGoto(n)}
            disabled={!clickable}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex min-h-11 items-center gap-2.5 rounded-none border px-3 py-2 text-left transition-colors",
              active
                ? "border-[var(--gold)] bg-[var(--ink-2)]"
                : done
                  ? "cursor-pointer border-[var(--line)] hover:border-[var(--gold)]"
                  : "cursor-not-allowed border-[var(--line-soft)] opacity-60",
            )}
          >
            <span
              className={cn(
                "mono flex size-6 shrink-0 items-center justify-center rounded-none border text-[0.6875rem]",
                active
                  ? "border-[var(--gold)] text-[var(--gold)]"
                  : done
                    ? "border-[var(--gold)] bg-[var(--gold)] text-[var(--ink)]"
                    : "border-[var(--line)] text-[var(--mute-2)]",
              )}
            >
              {done ? "✓" : n}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="mono text-[0.5625rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
                Шаг {n}
              </span>
              <span
                className={cn(
                  "truncate text-[0.8125rem]",
                  active ? "text-[var(--paper)]" : "text-[var(--paper-dim)]",
                )}
              >
                {WIZARD_STEP_LABELS[n]}
              </span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
