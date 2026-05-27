import { forwardRef } from "react";
import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** Мелкий mono-тег над заголовком (uppercase). */
  tag?: ReactNode;
  /** Заголовок карточки (display-serif). */
  title?: ReactNode;
  /** Описание под заголовком. */
  desc?: ReactNode;
  /** Мета-строка снизу (статус, дата). */
  meta?: ReactNode;
  /** Подсветить золотой бордер по hover (для кликабельных карточек). */
  interactive?: boolean;
  /** Уплотнить отступы (для плотных списков/студии). */
  dense?: boolean;
}

/**
 * Sumi-карточка. Подложка `--ink-2` поверх Kuro, прямые углы, тонкий Hai-бордер.
 * Глубина — слоями подложек, без box-shadow. Слоты: tag / title / desc / meta +
 * произвольный children. border-on-hover опционально через `interactive`.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { tag, title, desc, meta, interactive, dense, className, children, ...rest },
  ref,
) {
  const hasHeader = tag || title || desc;
  return (
    <div
      ref={ref}
      className={cn(
        "rounded-none border border-[var(--line-soft)] bg-[var(--ink-2)] text-[var(--paper)]",
        dense ? "p-4" : "p-6 md:p-8",
        interactive &&
          "transition-colors duration-300 hover:border-[var(--gold)] focus-within:border-[var(--gold)]",
        className,
      )}
      {...rest}
    >
      {hasHeader && (
        <div className={cn(children && (dense ? "mb-3" : "mb-4"))}>
          {tag && (
            <div className="mb-2 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--copper,var(--ember))]">
              {tag}
            </div>
          )}
          {title && (
            <h3 className="font-[family-name:var(--font-display)] text-lg font-semibold leading-tight text-[var(--paper)]">
              {title}
            </h3>
          )}
          {desc && (
            <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">{desc}</p>
          )}
        </div>
      )}

      {children}

      {meta && (
        <div className="mt-4 border-t border-[var(--line-soft)] pt-3 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.12em] text-[var(--mute)]">
          {meta}
        </div>
      )}
    </div>
  );
});
