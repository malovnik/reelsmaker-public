import type { ReactNode } from "react";
import { cn } from "./cn";

/** Бейджи честности из спеки d3 §5 + обычные статусы. */
export type HonestyBadge =
  | "opt-in"
  | "off-default"
  | "cpu-heavy"
  | "dormant"
  | "decorative"
  | "broken"
  | "partial"
  | "destructive";

export type StatusBadge = "neutral" | "success" | "warning" | "danger" | "accent";

export type BadgeVariant = HonestyBadge | StatusBadge;

export interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  /** Пиксельный шрифт Press Start 2P (для honesty-чипов из спеки). */
  pixel?: boolean;
  className?: string;
  title?: string;
}

/** Русские лейблы honesty-бейджей по умолчанию (если children не передан явно). */
export const HONESTY_LABELS: Record<HonestyBadge, string> = {
  "opt-in": "ПО ЖЕЛАНИЮ",
  "off-default": "ВЫКЛ. ПО УМОЛЧАНИЮ",
  "cpu-heavy": "ГРУЗИТ ПРОЦЕССОР",
  dormant: "СЧИТАЕТ ВПУСТУЮ",
  decorative: "НИЧЕГО НЕ МЕНЯЕТ",
  broken: "НЕ РАБОТАЕТ",
  partial: "РАБОТАЕТ ЧАСТИЧНО",
  destructive: "НЕОБРАТИМО",
};

// Палитра по спеке: Kasumi / Dō (copper) / Chi (danger)
const variantStyles: Record<BadgeVariant, string> = {
  // honesty
  "opt-in": "border-[var(--line)] text-[var(--mute-2)]",
  "off-default": "border-[var(--line)] text-[var(--mute-2)]",
  "cpu-heavy": "border-[var(--copper,var(--ember))] text-[var(--copper,var(--ember))]",
  dormant: "border-[var(--copper,var(--ember))] text-[var(--copper,var(--ember))]",
  decorative: "border-[var(--danger)] text-[var(--danger)]",
  broken: "border-[var(--danger)] text-[var(--danger)]",
  partial: "border-[var(--danger)] text-[var(--danger)]",
  destructive: "border-[var(--danger)] text-[var(--danger)]",
  // status
  neutral: "border-[var(--line)] text-[var(--mute-2)]",
  success: "border-[var(--success)] text-[var(--success)]",
  warning: "border-[var(--warning)] text-[var(--warning)]",
  danger: "border-[var(--danger)] text-[var(--danger)]",
  accent: "border-[var(--gold)] text-[var(--gold)]",
};

/**
 * Текст-чип статуса/честности. Прямые углы, тонкий цветной бордер,
 * прозрачный фон. honesty-варианты подсвечивают фиктивные/опасные ручки.
 */
export function Badge({ variant = "neutral", children, pixel, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-none border bg-transparent leading-none",
        pixel
          ? "px-1.5 py-1 font-[family-name:var(--font-mono)] text-[9px] uppercase tracking-[0.1em]"
          : "px-2 py-0.5 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.12em]",
        variantStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
