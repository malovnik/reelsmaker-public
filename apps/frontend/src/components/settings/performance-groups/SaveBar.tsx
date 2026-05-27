
export type SaveStatus =
  | { kind: "pristine" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

interface SaveBarProps {
  status: SaveStatus;
  isDirty: boolean;
  isPending: boolean;
  onSave: () => void;
  onReset: () => void;
}

export function SaveBar({
  status,
  isDirty,
  isPending,
  onSave,
  onReset,
}: SaveBarProps) {
  const visible =
    isDirty ||
    status.kind === "saving" ||
    status.kind === "saved" ||
    status.kind === "error";

  if (!visible) return null;

  return (
    <div
      role="status"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-overlay)] backdrop-blur"
    >
      <div className="page-shell flex items-center justify-between gap-4 !py-3">
        <span className="text-xs text-[color:var(--text-secondary)]">
          {status.kind === "saving" && "Сохраняем…"}
          {status.kind === "saved" && (
            <span className="font-medium text-[color:var(--success)]">
              Сохранено
            </span>
          )}
          {status.kind === "error" && (
            <span className="text-[color:var(--danger)]">
              Не получилось сохранить — {status.message}
            </span>
          )}
          {(status.kind === "dirty" || status.kind === "pristine") &&
            isDirty &&
            "Есть несохранённые изменения"}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            disabled={!isDirty || isPending}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)] disabled:opacity-40"
          >
            Откатить
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!isDirty || isPending}
            className="rounded-lg bg-[color:var(--accent-primary)] px-4 py-1.5 text-xs font-semibold text-[color:var(--accent-on-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)] disabled:shadow-none"
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
