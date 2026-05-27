import { useCallback, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "./cn";

export type ModalSize = "sm" | "md" | "lg";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Заголовок (display-serif). Привязывается к aria-labelledby. */
  title: ReactNode;
  /** Подзаголовок под заголовком. */
  subtitle?: ReactNode;
  /** Содержимое скролл-области. */
  children: ReactNode;
  /** Содержимое sticky-футера (обычно кнопки). */
  footer?: ReactNode;
  size?: ModalSize;
  /** role диалога: `dialog` (обычный) или `alertdialog` (требует решения). */
  role?: "dialog" | "alertdialog";
  /** Точечный верхний бордер --danger (для деструктивных диалогов). */
  danger?: boolean;
  /** Закрывать по клику на оверлей (по умолчанию true; false для alertdialog). */
  closeOnOverlay?: boolean;
  /** Селектор/ref элемента для автофокуса при открытии. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

const sizes: Record<ModalSize, string> = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
};

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Модальное окно: фокус-трап, Esc, restore-focus, max-h-85vh со скроллом тела
 * и sticky header/footer. Прямые углы, Sumi-карточка на затемнённом оверлее.
 * Чистая презентация — состояние open/onClose контролирует вызывающий.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = "md",
  role = "dialog",
  danger,
  closeOnOverlay = true,
  initialFocusRef,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useRef(`modal-title-${Math.random().toString(36).slice(2)}`).current;

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      );
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    const focusTarget =
      initialFocusRef?.current ??
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE) ??
      panelRef.current;
    focusTarget?.focus();

    return () => {
      document.body.style.overflow = overflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open, initialFocusRef]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4"
      onKeyDown={handleKeyDown}
    >
      <div
        className="absolute inset-0 bg-[oklch(0.10_0_0/0.7)] backdrop-blur-sm"
        aria-hidden="true"
        onClick={closeOnOverlay ? onClose : undefined}
      />

      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "relative flex max-h-[85vh] w-full flex-col rounded-none border bg-[var(--ink-2)] outline-none",
          danger ? "border-[var(--line)] border-t-2 border-t-[var(--danger)]" : "border-[var(--line)]",
          sizes[size],
        )}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--line-soft)] bg-[var(--ink-2)] px-6 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="font-[family-name:var(--font-display)] text-lg font-semibold leading-tight text-[var(--paper)]"
            >
              {title}
            </h2>
            {subtitle && (
              <p className="mt-1 text-[0.875rem] leading-snug text-[var(--mute)]">{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="-mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-none text-[var(--mute-2)] transition-colors hover:bg-[var(--ink-3)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {footer && (
          <footer className="sticky bottom-0 z-10 flex items-center justify-end gap-3 border-t border-[var(--line-soft)] bg-[var(--ink-2)] px-6 py-4">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
