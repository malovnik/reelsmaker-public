/**
 * ToastContext — очередь тостов поверх презентационных Toast/ToastViewport.
 *
 * Закрывает FA3-03. Стек ≤3 видимых, остальные ждут в очереди; aria-live
 * наследуется от примитива Toast (role=alert для error, status для остальных).
 * Метод `error` принимает HumanError из humanizeError → title/detail/«Подробнее».
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { Toast, ToastViewport } from "@/components/ui";
import type { ToastData } from "@/components/ui";
import { humanizeError, type HumanError } from "@/lib/humanizeError";

/** Сколько тостов рендерим одновременно; остальные ждут в очереди. */
const MAX_VISIBLE = 3;

export interface ToastOptions {
  detail?: ReactNode;
  /** Полный текст под «Подробнее» (актуально для ошибок). */
  more?: ReactNode;
  duration?: number;
}

export interface ToastContextValue {
  success: (title: ReactNode, options?: ToastOptions) => string;
  info: (title: ReactNode, options?: ToastOptions) => string;
  error: (title: ReactNode, options?: ToastOptions) => string;
  /** Готовый показ ошибки из humanizeError(err): title + detail + hint. */
  showError: (err: unknown) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let counter = 0;
function nextId(): string {
  counter += 1;
  return `toast-${counter}-${Date.now()}`;
}

export interface ToastProviderProps {
  children: ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [queue, setQueue] = useState<ToastData[]>([]);
  const dismissRef = useRef<(id: string) => void>(() => {});

  const dismiss = useCallback((id: string) => {
    setQueue((prev) => prev.filter((t) => t.id !== id));
  }, []);
  dismissRef.current = dismiss;

  const push = useCallback(
    (type: ToastData["type"], title: ReactNode, options?: ToastOptions): string => {
      const id = nextId();
      setQueue((prev) => [
        ...prev,
        {
          id,
          type,
          title,
          detail: options?.detail,
          more: options?.more,
          duration: options?.duration,
        },
      ]);
      return id;
    },
    [],
  );

  const showError = useCallback(
    (err: unknown): string => {
      const human: HumanError = humanizeError(err);
      return push("error", human.title, {
        detail: human.detail,
        more: human.hint,
      });
    },
    [push],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      success: (title, options) => push("success", title, options),
      info: (title, options) => push("info", title, options),
      error: (title, options) => push("error", title, options),
      showError,
      dismiss,
    }),
    [push, showError, dismiss],
  );

  const visible = queue.slice(0, MAX_VISIBLE);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport>
        {visible.map((toast) => (
          <Toast key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </ToastViewport>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}
