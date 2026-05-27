import { useCallback, useEffect, useState } from "react";
import { api, type ProxyEntry, type ProxyListResponse } from "@/lib/api";

/**
 * R8.1 — UI управления кэшем proxy-файлов: список, LRU-cleanup, удаление
 * по source-хэшу. Бэк: /api/v1/proxies.
 */
export function ProxyCacheManager() {
  const [data, setData] = useState<ProxyListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.listProxies());
    } catch (err) {
      setError(`Не удалось загрузить список: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleCleanup() {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await api.cleanupProxies();
      setNotice(
        `Очистка завершена: удалено ${res.deleted}, освобождено ${res.freed_mb} МБ (лимит ${res.requested_max_gb} ГБ).`,
      );
      await reload();
    } catch (err) {
      setError(`Очистка не удалась: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(entry: ProxyEntry) {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await api.deleteProxy(entry.sha256);
      setNotice(`Удалён proxy ${entry.sha256.slice(0, 12)}…`);
      await reload();
    } catch (err) {
      setError(`Не удалось удалить: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="surface-card flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            Кэш proxy-файлов
          </h2>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Облегчённые копии исходников для быстрой обработки.
            {data &&
              ` Всего ${data.total_count} файлов · ${data.total_size_mb} МБ.`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={reload}
            disabled={busy || loading}
            className="rounded-lg border border-[color:var(--line-soft)] px-3 py-2 text-xs font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)] disabled:opacity-50"
          >
            Обновить
          </button>
          <button
            type="button"
            onClick={handleCleanup}
            disabled={busy || loading || !data || data.total_count === 0}
            className="rounded-lg border border-[color:var(--line-soft)] px-3 py-2 text-xs font-semibold text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--ink-2)] disabled:opacity-50"
          >
            {busy ? "Чистим…" : "Очистить (LRU)"}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-[color:var(--danger,#b91c1c)] bg-[color:var(--danger,#b91c1c)]/10 px-3 py-2 text-xs text-[color:var(--danger,#b91c1c)]">
          {error}
        </p>
      )}
      {notice && (
        <p className="rounded-lg border border-[color:var(--line-soft)] px-3 py-2 text-xs text-[color:var(--text-secondary)]">
          {notice}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-[color:var(--text-muted)]">Загрузка…</p>
      ) : data && data.items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[color:var(--text-muted)]">
              <tr className="border-b border-[color:var(--line-soft)]">
                <th className="py-2 pr-3 font-medium">Source (sha256)</th>
                <th className="py-2 pr-3 font-medium">Профиль</th>
                <th className="py-2 pr-3 font-medium">Размер</th>
                <th className="py-2 pr-3 font-medium">Возраст</th>
                <th className="py-2 pr-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry) => (
                <tr
                  key={`${entry.sha256}-${entry.profile_id}`}
                  className="border-b border-[color:var(--line-soft)]/50"
                >
                  <td className="py-2 pr-3 font-mono">
                    {entry.sha256.slice(0, 16)}…
                  </td>
                  <td className="py-2 pr-3">{entry.profile_id}</td>
                  <td className="py-2 pr-3">{entry.file_size_mb} МБ</td>
                  <td className="py-2 pr-3">
                    {formatAge(entry.age_sec)}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleDelete(entry)}
                      disabled={busy}
                      className="text-[color:var(--danger,#b91c1c)] transition-opacity hover:opacity-70 disabled:opacity-40"
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-[color:var(--text-muted)]">
          Кэш пуст — proxy-файлов нет.
        </p>
      )}
    </section>
  );
}

function formatAge(sec: number): string {
  if (sec < 60) return `${Math.round(sec)} сек`;
  if (sec < 3600) return `${Math.round(sec / 60)} мин`;
  if (sec < 86400) return `${Math.round(sec / 3600)} ч`;
  return `${Math.round(sec / 86400)} дн`;
}
