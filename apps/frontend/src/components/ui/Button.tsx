import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Иконка слева от текста (пиксельная/инлайн-svg). */
  iconLeft?: ReactNode;
  /** Иконка справа от текста. */
  iconRight?: ReactNode;
  /** Растянуть на всю ширину контейнера. */
  block?: boolean;
  /** Показать индикатор занятости и заблокировать клики. */
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-none border font-medium " +
  "whitespace-nowrap select-none transition-[background-color,border-color,color,transform] duration-200 " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)] " +
  "disabled:cursor-not-allowed disabled:opacity-50 active:translate-y-px";

const sizes: Record<ButtonSize, string> = {
  // тач-таргет ≥44px по высоте на всех размерах
  sm: "min-h-11 px-3 text-[0.8125rem]",
  md: "min-h-11 px-4 text-[0.875rem]",
  lg: "min-h-12 px-6 text-[0.9375rem]",
};

const variants: Record<ButtonVariant, string> = {
  // золотая обводка → заливка по hover
  primary:
    "border-[var(--gold)] bg-transparent text-[var(--gold)] " +
    "hover:bg-[var(--gold)] hover:text-[var(--ink)]",
  secondary:
    "border-[var(--line)] bg-[var(--ink-2)] text-[var(--paper)] " +
    "hover:border-[var(--mute)] hover:bg-[var(--ink-3)]",
  ghost:
    "border-transparent bg-transparent text-[var(--mute-2)] " +
    "hover:text-[var(--paper)] hover:bg-[var(--ink-2)]",
  danger:
    "border-[var(--danger)] bg-transparent text-[var(--danger)] " +
    "hover:bg-[var(--danger)] hover:text-[var(--paper)]",
};

/**
 * Базовая кнопка дизайн-системы. Прямые углы, токены через var(--*),
 * focus-visible-обводка, тач-таргет ≥44px. Чистая презентация.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    iconLeft,
    iconRight,
    block,
    loading,
    disabled,
    className,
    children,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(base, sizes[size], variants[variant], block && "w-full", className)}
      {...rest}
    >
      {loading ? (
        <span className="inline-flex items-center gap-1" aria-hidden="true">
          <span className="size-1.5 animate-pulse rounded-none bg-current" />
          <span className="size-1.5 animate-pulse rounded-none bg-current [animation-delay:150ms]" />
          <span className="size-1.5 animate-pulse rounded-none bg-current [animation-delay:300ms]" />
        </span>
      ) : (
        iconLeft && <span className="inline-flex shrink-0">{iconLeft}</span>
      )}
      {children && <span>{children}</span>}
      {!loading && iconRight && <span className="inline-flex shrink-0">{iconRight}</span>}
    </button>
  );
});
