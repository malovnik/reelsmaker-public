
import type { ReactNode } from "react";

/**
 * Fieldset-обёртка с заголовком для группы связанных настроек.
 *
 * Shared settings primitive. Используется как drop-in замена локальным
 * определениям в *SettingsClient.tsx (план Phase 8.3-8.6 декомпозиции).
 */
export function Group({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="surface-card p-5">
      <legend className="px-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
        {title}
      </legend>
      <div className="flex flex-col gap-5 pt-2">{children}</div>
    </fieldset>
  );
}
