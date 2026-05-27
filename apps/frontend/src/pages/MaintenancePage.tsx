import { ProxyCacheManager } from "@/components/maintenance/ProxyCacheManager";
import { FontsRefresh } from "@/components/maintenance/FontsRefresh";

/**
 * R8.1 + R8.2 — Эксперт-режим: обслуживание кэшей.
 * Управление кэшем proxy-файлов (list/cleanup/delete) + ручное обновление
 * кэша шрифтов.
 */
export default function MaintenancePage() {
  return (
    <div className="flex flex-col gap-8 pb-24">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">Обслуживание</h1>
        <p className="page-subtitle">
          Эксперт-режим. Управление кэшами proxy-файлов и шрифтов. Изменения
          применяются сразу и не требуют перезапуска сервера.
        </p>
      </header>

      <ProxyCacheManager />
      <FontsRefresh />
    </div>
  );
}
