import { Button } from "@/components/ui";

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
      className="fixed inset-x-0 bottom-0 z-30 border-t border-[color:var(--line)] bg-[color:var(--ink-2)] backdrop-blur"
    >
      <div className="page-shell flex items-center justify-between gap-4 !py-3">
        <span className="text-xs text-[color:var(--mute-2)]">
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
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            disabled={!isDirty || isPending}
          >
            Откатить
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onSave}
            disabled={!isDirty || isPending}
          >
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  );
}
