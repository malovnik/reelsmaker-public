import { useLoaderData } from "react-router-dom";
import { api, type PerformanceSettings } from "@/lib/api";
import { PerformanceSettingsClient } from "@/components/PerformanceSettingsClient";

export async function loader(): Promise<PerformanceSettings | null> {
  try {
    return await api.getPerformanceSettings();
  } catch {
    return null;
  }
}

export default function PerformanceSettingsPage() {
  const initial = useLoaderData() as PerformanceSettings | null;
  return (
    <div className="flex flex-col gap-8 pb-24">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Производительность
        </h1>
        <p className="page-subtitle">
          Параллельные процессы, параметры рабочей копии, лимиты кэша.
          Изменения применятся к следующим нарезкам без перезапуска сервера.
        </p>
      </header>

      {initial === null ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Настройки не загрузились. Запусти{" "}
          <code className="font-mono">./run.sh</code> и обнови страницу.
        </div>
      ) : (
        <PerformanceSettingsClient initial={initial} />
      )}
    </div>
  );
}
