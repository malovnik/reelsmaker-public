import { useId } from "react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  /** Видимая метка тумблера. */
  label: ReactNode;
  /**
   * ОБЯЗАТЕЛЬНАЯ инлайн-подсказка (Эксперт-режим: «подсказка напротив каждого
   * контрола»). Всегда видима под меткой. Контрол нельзя собрать без неё.
   */
  hint: ReactNode;
  /** Доп. узел справа от метки (бейдж честности, иконка-(i) тултипа). */
  adornment?: ReactNode;
  disabled?: boolean;
  className?: string;
  id?: string;
}

/**
 * Тоггл-переключатель. Прямые углы, золотой трек во включённом состоянии.
 * `hint` обязателен — гарантирует подсказку у каждого контрола.
 */
export function Switch({
  checked,
  onCheckedChange,
  label,
  hint,
  adornment,
  disabled,
  className,
  id,
}: SwitchProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;

  return (
    <div className={cn("flex items-start justify-between gap-4", className)}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <label
            htmlFor={fieldId}
            className={cn(
              "text-[0.9375rem] font-medium text-[var(--paper)]",
              disabled && "opacity-50",
            )}
          >
            {label}
          </label>
          {adornment}
        </div>
        <p id={hintId} className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
          {hint}
        </p>
      </div>

      <button
        type="button"
        role="switch"
        id={fieldId}
        aria-checked={checked}
        aria-describedby={hintId}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-none border " +
            "transition-colors duration-200 " +
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)] " +
            "disabled:cursor-not-allowed disabled:opacity-50",
          checked
            ? "border-[var(--gold)] bg-[var(--gold)]"
            : "border-[var(--line)] bg-[var(--ink-3)]",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "block h-4 w-4 rounded-none transition-transform duration-200",
            checked ? "translate-x-6 bg-[var(--ink)]" : "translate-x-1 bg-[var(--mute-2)]",
          )}
        />
      </button>
    </div>
  );
}
