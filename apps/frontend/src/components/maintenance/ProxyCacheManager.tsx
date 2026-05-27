import { useCallback, useEffect, useState } from "react";
import { api, type ProxyEntry, type ProxyListResponse } from "@/lib/api";
import { Button } from "@/components/ui";
import { ActionButton } from "@/components/settings-shared";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";

/**
 * Управление кэшем рабочих копий: список, очистка по объёму, точечное
 * удаление. Ошибки — через useToast.showError, удаление — через useConfirm.
 */
export function ProxyCacheManager() {
  const toast = useToast();
  const confirm = useConfirm();
  const [data, setData] = useState<ProxyListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.listProxies());
    } catch (err) {
      toast.showError(err);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleCleanup() {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api.cleanupProxies();
      toast.success("Кэш очищен", {
        detail: `Удалено ${res.deleted} · освобождено ${res.freed_mb} МБ (лимит ${res.requested_max_gb} ГБ).`,
      });
      await reload();
    } catch (err) {
      toast.showError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(entry: ProxyEntry) {
    if (busy) return;
    const ok = await confirm({
      title: "Удалить рабочую копию?",
      description:
        "Файл уберётся из кэша. При следующей обработке этого исходника копия пересоздастся заново.",
      confirmLabel: "Удалить",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.deleteProxy(entry.sha256);
      toast.success(`Удалена копия ${entry.sha256.slice(0, 12)}…`);
      await reload();
    } catch (err) {
      toast.showError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-none border border-[var(--line)] bg-[var(--ink-2)] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-[family-name:var(--font-serif)] text-[1.0625rem] font-bold text-[var(--paper)]">
            Кэш рабочих копий
          </h2>
          <p className="mt-1 text-[0.8125rem] leading-snug text-[var(--mute)]">
            Облегчённые копии исходников для быстрой обработки.
            {data &&
              ` Всего ${data.total_count} файлов · ${data.total_size_mb} МБ.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" disabled={busy || loading} onClick={reload}>
            Обновить
          </Button>
          <ActionButton
            variant="secondary"
            size="sm"
            hintKey="proxy_cleanup"
            disabled={busy || loading || !data || data.total_count === 0}
            loading={busy}
            onClick={handleCleanup}
          >
            Очистить (старые первыми)
          </ActionButton>
        </div>
      </div>

      {loading ? (
        <p className="mt-4 text-[0.875rem] text-[var(--mute)]">Загрузка…</p>
      ) : data && data.items.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-[0.8125rem]">
            <thead className="text-[var(--mute)]">
              <tr className="border-b border-[var(--line)]">
                <th className="py-2 pr-3 font-medium">Источник (хэш)</th>
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
                  className="border-b border-[var(--line)] text-[var(--mute-2)]"
                >
                  <td className="py-2 pr-3 font-[family-name:var(--font-mono)]">
                    {entry.sha256.slice(0, 16)}…
                  </td>
                  <td className="py-2 pr-3">{entry.profile_id}</td>
                  <td className="py-2 pr-3">{entry.file_size_mb} МБ</td>
                  <td className="py-2 pr-3">{formatAge(entry.age_sec)}</td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleDelete(entry)}
                      disabled={busy}
                      className="text-[var(--danger)] transition-opacity hover:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--danger)] disabled:opacity-40"
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
        <p className="mt-4 text-[0.875rem] text-[var(--mute)]">
          Кэш пуст — рабочих копий нет.
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
