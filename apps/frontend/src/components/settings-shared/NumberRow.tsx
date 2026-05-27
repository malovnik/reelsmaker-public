
export interface NumericProps {
  id: string;
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.max(min, Math.min(max, value));
}

/**
 * Числовой input с меткой, подсказкой и единицей измерения.
 *
 * Shared settings primitive. Используется как drop-in замена локальным
 * определениям в *SettingsClient.tsx (план Phase 8.3-8.6 декомпозиции).
 */
export function NumberRow({
  id,
  label,
  hint,
  value,
  min,
  max,
  step,
  unit,
  disabled,
  onChange,
}: NumericProps) {
  return (
    <div className={disabled ? "opacity-50" : undefined}>
      <div className="flex items-baseline justify-between gap-3">
        <label
          htmlFor={id}
          className="text-sm text-[color:var(--text-primary)]"
        >
          {label}
        </label>
        <span className="font-mono text-sm tabular-nums text-[color:var(--text-secondary)]">
          {value}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(clamp(Number(e.target.value), min, max))}
        aria-describedby={`${id}-hint`}
        className="mt-2 block w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 font-mono text-sm tabular-nums text-[color:var(--text-primary)] outline-none focus-visible:border-[color:var(--accent-primary)] focus-visible:ring-2 focus-visible:ring-[color:var(--accent-primary-subtle)] disabled:cursor-not-allowed"
      />
      <p
        id={`${id}-hint`}
        className="mt-1.5 text-xs text-[color:var(--text-muted)]"
      >
        {hint}{" "}
        <span className="text-[color:var(--text-disabled)]">
          ({min}–{max})
        </span>
      </p>
    </div>
  );
}
