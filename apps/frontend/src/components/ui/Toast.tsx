import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export type ToastType = "success" | "error" | "info";

export interface ToastData {
  id: string;
  type: ToastType;
  title: ReactNode;
  /** Доп. строка под заголовком. */
  detail?: ReactNode;
  /** Полный текст под «Подробнее» (для error из humanizeError). */
  more?: ReactNode;
  /** Длительность автоскрытия, мс. По умолчанию success/info=4000, error=8000. */
  duration?: number;
}

export interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const accent: Record<ToastType, string> = {
  success: "var(--gold)",
  error: "var(--danger)",
  info: "var(--copper,var(--ember))",
};

const icons: Record<ToastType, ReactNode> = {
  success: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  error: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 7.5v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="4.8" r="0.9" fill="currentColor" />
    </svg>
  ),
};

/**
 * Презентационный тост. Пауза автоскрытия на hover, «Подробнее» для ошибок,
 * aria-live. Очередь и стейт подключает внешний ToastProvider (другой агент).
 */
export function Toast({ toast, onDismiss }: ToastProps) {
  const { id, type, title, detail, more } = toast;
  const [expanded, setExpanded] = useState(false);
  const paused = useRef(false);
  const remaining = useRef(toast.duration ?? (type === "error" ? 8000 : 4000));
  const startedAt = useRef(0);

  useEffect(() => {
    let timer: number;
    const run = () => {
      startedAt.current = Date.now();
      timer = window.setTimeout(() => onDismiss(id), remaining.current);
    };
    if (!paused.current) run();
    return () => window.clearTimeout(timer);
  }, [id, onDismiss, expanded]);

  const onEnter = () => {
    paused.current = true;
    remaining.current -= Date.now() - startedAt.current;
  };
  const onLeave = () => {
    paused.current = false;
    setExpanded((v) => v);
  };

  return (
    <div
      role={type === "error" ? "alert" : "status"}
      aria-live={type === "error" ? "assertive" : "polite"}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      className={cn(
        "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-none border bg-[var(--ink-2)] px-4 py-3",
        "motion-safe:animate-[slide-in_0.2s_ease-out]",
        type === "error" ? "border-[var(--line)] border-l-2 border-l-[var(--danger)]" : "border-[var(--line)]",
      )}
    >
      <span className="mt-0.5 shrink-0" style={{ color: accent[type] }} aria-hidden="true">
        {icons[type]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[0.9375rem] font-medium leading-snug text-[var(--paper)]">{title}</p>
        {detail && <p className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">{detail}</p>}
        {more && (
          <>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.1em] text-[var(--mute-2)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
            >
              {expanded ? "Свернуть" : "Подробнее"}
            </button>
            {expanded && (
              <p className="mt-1 text-[0.8125rem] leading-snug text-[var(--mute)]">{more}</p>
            )}
          </>
        )}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(id)}
        aria-label="Закрыть уведомление"
        className="-mr-1 -mt-1 inline-flex size-8 shrink-0 items-center justify-center rounded-none text-[var(--mute-2)] transition-colors hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      </button>
    </div>
  );
}

export interface ToastViewportProps {
  children: ReactNode;
  className?: string;
}

/** Контейнер для стека тостов: низ-право (desktop) / низ-центр (mobile). */
export function ToastViewport({ children, className }: ToastViewportProps) {
  return (
    <div
      className={cn(
        "pointer-events-none fixed inset-x-0 bottom-0 z-[250] flex flex-col items-center gap-2 p-4",
        "sm:inset-x-auto sm:right-0 sm:items-end",
        className,
      )}
    >
      {children}
    </div>
  );
}
