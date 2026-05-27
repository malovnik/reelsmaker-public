/**
 * WizardStateProvider (R2) — поднимает состояние визарда НАД деревом режимов.
 *
 * Проблема: guided и expert — два разных поддерева над локальным
 * useWizardState. Переключение режима размонтирует активное поддерево и
 * обнуляет состояние (включая выбранный File, project_id, опции). Решение —
 * вызвать useWizardState один раз здесь, выше обоих режимов, и раздать его
 * результат через контекст. Тогда guided и expert читают/пишут один источник,
 * и переключение не теряет данные.
 *
 * Контракт хранит ту же модель данных, что и useWizardState
 * (WizardState + WizardActions), чтобы оба режима работали с ней без адаптеров.
 */
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import {
  useWizardState,
  type UseWizardStateOptions,
  type WizardActions,
  type WizardState,
} from "@/components/upload/useWizardState";

export interface WizardStateContextValue {
  state: WizardState;
  actions: WizardActions;
}

const WizardStateContext = createContext<WizardStateContextValue | null>(null);

export interface WizardStateProviderProps extends UseWizardStateOptions {
  children: ReactNode;
}

export function WizardStateProvider({
  children,
  ...options
}: WizardStateProviderProps) {
  const value = useWizardState(options);

  return (
    <WizardStateContext.Provider value={value}>
      {children}
    </WizardStateContext.Provider>
  );
}

export function useWizardStateContext(): WizardStateContextValue {
  const ctx = useContext(WizardStateContext);
  if (!ctx) {
    throw new Error(
      "useWizardStateContext must be used within <WizardStateProvider>",
    );
  }
  return ctx;
}
