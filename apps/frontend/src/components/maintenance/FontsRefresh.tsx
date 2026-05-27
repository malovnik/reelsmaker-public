import { useState } from "react";
import { api } from "@/lib/api";

/**
 * R8.2 — ручное обновление кэша шрифтов (POST /settings/fonts/refresh).
 * Пересканирует системные/проектные шрифты без перезапуска сервера.
 */
export function FontsRefresh() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRefresh() {
    if (busy) return;
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.refreshFonts();
      setResult(`Кэш шрифтов обновлён: найдено ${res.fonts.length} шрифтов.`);
    } catch (err) {
      setError(`Не удалось обновить шрифты: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="surface-card flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            Кэш шрифтов
          </h2>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Пересканировать доступные шрифты после установки новых в систему.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={busy}
          className="rounded-lg border border-[color:var(--line-soft)] px-3 py-2 text-xs font-semibold text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--ink-2)] disabled:opacity-50"
        >
          {busy ? "Обновляем…" : "Обновить шрифты"}
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-[color:var(--danger,#b91c1c)] bg-[color:var(--danger,#b91c1c)]/10 px-3 py-2 text-xs text-[color:var(--danger,#b91c1c)]">
          {error}
        </p>
      )}
      {result && (
        <p className="rounded-lg border border-[color:var(--line-soft)] px-3 py-2 text-xs text-[color:var(--text-secondary)]">
          {result}
        </p>
      )}
    </section>
  );
}
