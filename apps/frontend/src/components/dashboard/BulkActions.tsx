
interface Props {
  selectedIds: string[];
  onDelete: () => void;
  onClearSelection: () => void;
}

export function BulkActions({ selectedIds, onDelete, onClearSelection }: Props) {
  if (selectedIds.length === 0) return null;
  return (
    <div className="sticky top-14 z-30 flex items-center justify-between gap-3 rounded-lg border border-[color:var(--accent-primary)]/30 bg-[color:var(--accent-primary-subtle)] px-4 py-3 shadow-[var(--shadow-sm)]">
      <div className="text-sm text-[color:var(--text-primary)]">
        Выбрано: <strong>{selectedIds.length}</strong>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onClearSelection}
          className="rounded-md px-3 py-1.5 text-sm text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
        >
          Снять выбор
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="btn btn-danger"
        >
          Удалить выбранные
        </button>
      </div>
    </div>
  );
}
