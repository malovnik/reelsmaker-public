import type { HintSource } from "./hintAdornment";
import { resolveHint } from "./hintAdornment";

export interface NumericProps extends HintSource {
  id: string;
  label: string;
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
 * Числовое поле с обязательной подсказкой (Эксперт-студия §2). Прямые углы,
 * фокус → золото, моноширинное значение. `hintKey` → триплет из реестра.
 */
export function NumberRow({
  id,
  label,
  hintKey,
  hint,
  value,
  min,
  max,
  step,
  unit,
  disabled,
  onChange,
}: NumericProps) {
  const { inline, adornment, badgeNode } = resolveHint({ hintKey, hint });
  const hintId = `${id}-hint`;
  return (
    <div className={disabled ? "opacity-50" : undefined}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label
            htmlFor={id}
            className="text-[0.9375rem] font-medium text-[var(--paper)]"
          >
            {label}
          </label>
          {badgeNode}
          {adornment}
        </div>
        <span className="font-[family-name:var(--font-mono)] text-[0.875rem] tabular-nums text-[var(--gold)]">
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
        aria-describedby={hintId}
        className="mt-2 block w-full rounded-none border border-[var(--line)] bg-[var(--ink)] px-[18px] py-[14px] font-[family-name:var(--font-mono)] text-[0.9375rem] tabular-nums text-[var(--paper)] outline-none transition-colors hover:border-[var(--mute)] focus:border-[var(--gold)] disabled:cursor-not-allowed"
      />
      <p id={hintId} className="mt-1.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
        {inline}{" "}
        <span className="text-[var(--mute-2)]">
          ({min}–{max})
        </span>
      </p>
    </div>
  );
}
