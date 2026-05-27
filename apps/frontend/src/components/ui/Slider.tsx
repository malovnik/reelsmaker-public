import { useId } from "react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export interface SliderProps {
  value: number;
  onValueChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  /** Видимая метка ползунка. */
  label: ReactNode;
  /**
   * ОБЯЗАТЕЛЬНАЯ инлайн-подсказка (Эксперт-режим). Всегда видима под меткой.
   */
  hint: ReactNode;
  /** Форматирует текущее значение для отображения (по умолчанию — число). */
  formatValue?: (value: number) => ReactNode;
  /** Доп. узел справа от метки (бейдж честности, иконка-(i)). */
  adornment?: ReactNode;
  disabled?: boolean;
  className?: string;
  id?: string;
}

/**
 * Ползунок. Нативный range (доступность, клавиатура), золотой трек заполнения
 * через прогресс-градиент, прямые углы. `hint` обязателен.
 */
export function Slider({
  value,
  onValueChange,
  min,
  max,
  step = 1,
  label,
  hint,
  formatValue,
  adornment,
  disabled,
  className,
  id,
}: SliderProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label htmlFor={fieldId} className="text-[0.9375rem] font-medium text-[var(--paper)]">
            {label}
          </label>
          {adornment}
        </div>
        <span className="font-[family-name:var(--font-mono)] text-[0.875rem] tabular-nums text-[var(--gold)]">
          {formatValue ? formatValue(value) : value}
        </span>
      </div>

      <input
        type="range"
        id={fieldId}
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-describedby={hintId}
        onChange={(e) => onValueChange(Number(e.target.value))}
        style={{
          background: `linear-gradient(to right, var(--gold) 0%, var(--gold) ${pct}%, var(--ink-3) ${pct}%, var(--ink-3) 100%)`,
        }}
        className={cn(
          "h-1.5 w-full cursor-pointer appearance-none rounded-none " +
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)] " +
            "disabled:cursor-not-allowed disabled:opacity-50 " +
            // thumb (webkit)
            "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 " +
            "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-none " +
            "[&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-[var(--gold)] " +
            "[&::-webkit-slider-thumb]:bg-[var(--paper)] " +
            // thumb (firefox)
            "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-none " +
            "[&::-moz-range-thumb]:border [&::-moz-range-thumb]:border-[var(--gold)] " +
            "[&::-moz-range-thumb]:bg-[var(--paper)]",
        )}
      />

      <p id={hintId} className="text-[0.8125rem] leading-snug text-[var(--mute)]">
        {hint}
      </p>
    </div>
  );
}
