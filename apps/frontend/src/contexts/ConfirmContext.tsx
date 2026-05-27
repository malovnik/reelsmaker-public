/**
 * ConfirmContext — промис-based замена window.confirm.
 *
 * Закрывает FA3-03 (13× window.confirm). `useConfirm()` возвращает функцию,
 * которая показывает <ConfirmDialog> и резолвит Promise<boolean>. Фокус-трап,
 * Esc=отмена и автофокус на «Отмена» уже внутри Modal/ConfirmDialog.
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
import { ConfirmDialog } from "@/components/ui";

export interface ConfirmOptions {
  title: ReactNode;
  /** Что именно произойдёт и обратимо ли. */
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Деструктивное действие → danger-стиль модалки. */
  destructive?: boolean;
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

interface PendingConfirm extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

export interface ConfirmProviderProps {
  children: ReactNode;
}

export function ConfirmProvider({ children }: ConfirmProviderProps) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const pendingRef = useRef<PendingConfirm | null>(null);
  pendingRef.current = pending;

  const confirm = useCallback<ConfirmFn>((options) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...options, resolve });
    });
  }, []);

  const settle = useCallback((result: boolean) => {
    const current = pendingRef.current;
    if (current) current.resolve(result);
    setPending(null);
  }, []);

  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        description={pending?.description ?? ""}
        confirmLabel={pending?.confirmLabel}
        cancelLabel={pending?.cancelLabel}
        destructive={pending?.destructive}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used within <ConfirmProvider>");
  }
  return ctx;
}
