/**
 * UiModeContext — режим раскрытия сложности: «Пошаговый» (guided) / «Эксперт».
 *
 * Закрывает FA3-01. Режим — прогрессивное раскрытие сложности, не разные
 * функции (роуты/данные идентичны). default = guided (новичок-first).
 * Persist в localStorage; чтение синхронно при инициализации (no-flash) —
 * раскладка не мигает при первом рендере.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

export type UiMode = "guided" | "expert";

const STORAGE_KEY = "reelibra.uiMode";
const DEFAULT_MODE: UiMode = "guided";

export interface UiModeContextValue {
  mode: UiMode;
  setMode: (mode: UiMode) => void;
  isGuided: boolean;
  isExpert: boolean;
}

const UiModeContext = createContext<UiModeContextValue | null>(null);

/** Синхронное чтение сохранённого режима (no-flash). */
function readStoredMode(): UiMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "guided" || stored === "expert") return stored;
  } catch {
    // localStorage недоступен (приватный режим/квота) — дефолт.
  }
  return DEFAULT_MODE;
}

export interface UiModeProviderProps {
  children: ReactNode;
}

export function UiModeProvider({ children }: UiModeProviderProps) {
  const [mode, setModeState] = useState<UiMode>(readStoredMode);

  const setMode = useCallback((next: UiMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // запись могла не пройти — состояние в памяти остаётся актуальным.
    }
  }, []);

  const value = useMemo<UiModeContextValue>(
    () => ({
      mode,
      setMode,
      isGuided: mode === "guided",
      isExpert: mode === "expert",
    }),
    [mode, setMode],
  );

  return <UiModeContext.Provider value={value}>{children}</UiModeContext.Provider>;
}

export function useUiMode(): UiModeContextValue {
  const ctx = useContext(UiModeContext);
  if (!ctx) {
    throw new Error("useUiMode must be used within <UiModeProvider>");
  }
  return ctx;
}
