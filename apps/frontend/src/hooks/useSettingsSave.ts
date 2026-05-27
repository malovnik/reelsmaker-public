
import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";

interface UseSettingsSaveOptions<T> {
  initial: T;
  save: (values: T) => Promise<void>;
  equals?: (a: T, b: T) => boolean;
}

interface UseSettingsSaveResult<T> {
  values: T;
  setValues: Dispatch<SetStateAction<T>>;
  dirty: boolean;
  busy: boolean;
  error: string | null;
  savedAt: number | null;
  handleSave: () => Promise<void>;
  handleReset: () => void;
}

/**
 * Инкапсулирует busy / error / savedAt / dirty tracking + handleSave / handleReset
 * для settings-клиентов. Заменяет дублирующийся паттерн из
 * PerformanceSettingsClient / PostProductionSettingsClient / SubtitleSettingsClient /
 * VisionProfilesSettingsClient (план Phase 8.3-8.6 декомпозиции).
 *
 * Usage:
 *   const s = useSettingsSave({ initial: settings, save: api.saveSettings });
 *   return <button onClick={s.handleSave} disabled={s.busy || !s.dirty}>...</button>;
 */
export function useSettingsSave<T>(
  options: UseSettingsSaveOptions<T>,
): UseSettingsSaveResult<T> {
  const { initial, save, equals } = options;
  const [values, setValues] = useState<T>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const dirty = useMemo(() => {
    if (equals) return !equals(values, initial);
    return JSON.stringify(values) !== JSON.stringify(initial);
  }, [values, initial, equals]);

  const handleSave = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await save(values);
      setSavedAt(Date.now());
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    } finally {
      setBusy(false);
    }
  }, [values, save]);

  const handleReset = useCallback(() => {
    setValues(initial);
    setError(null);
  }, [initial]);

  return {
    values,
    setValues,
    dirty,
    busy,
    error,
    savedAt,
    handleSave,
    handleReset,
  };
}
