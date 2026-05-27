import { useState } from "react";
import { api } from "@/lib/api";
import { ActionButton } from "@/components/settings-shared";
import { useToast } from "@/contexts/ToastContext";

/**
 * Ручное обновление кэша шрифтов. Пересканирует системные/проектные шрифты
 * без перезапуска сервера. Ошибки — через useToast.showError.
 */
export function FontsRefresh() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api.refreshFonts();
      toast.success("Кэш шрифтов обновлён", {
        detail: `Найдено ${res.fonts.length} шрифтов.`,
      });
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
            Кэш шрифтов
          </h2>
          <p className="mt-1 text-[0.8125rem] leading-snug text-[var(--mute)]">
            Пересканировать доступные шрифты после установки новых в систему.
          </p>
        </div>
        <ActionButton
          variant="secondary"
          size="sm"
          hintKey="fonts_refresh"
          loading={busy}
          onClick={handleRefresh}
        >
          Обновить шрифты
        </ActionButton>
      </div>
    </section>
  );
}
