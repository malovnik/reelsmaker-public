
import type { NumericProps } from "./NumberRow";

/**
 * Слайдер-range input с меткой и подсказкой.
 *
 * Shared settings primitive. Используется как drop-in замена локальным
 * определениям в *SettingsClient.tsx (план Phase 8.3-8.6 декомпозиции).
 */
export function SliderRow({
  id,
  label,
  hint,
  value,
  min,
  max,
  step,
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
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-describedby={`${id}-hint`}
        className="mt-2 block w-full accent-[color:var(--accent-primary)] disabled:cursor-not-allowed"
      />
      <p
        id={`${id}-hint`}
        className="mt-1.5 text-xs text-[color:var(--text-muted)]"
      >
        {hint}
      </p>
    </div>
  );
}
