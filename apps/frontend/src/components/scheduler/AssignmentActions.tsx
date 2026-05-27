import { Button } from "@/components/ui";
import type { ScheduleAssignment } from "@/lib/api/scheduler";

export interface AssignmentActionHandlers {
  onEdit: (a: ScheduleAssignment) => void;
  onCancel: (a: ScheduleAssignment) => void;
  onRetry: (a: ScheduleAssignment) => void;
  cancellingId: number | null;
  retryingId: number | null;
}

interface Props extends AssignmentActionHandlers {
  a: ScheduleAssignment;
  /** Расположить кнопки в строку (карточка mobile) или столбцом (таблица). */
  layout: "row" | "column";
}

/**
 * Действия над публикацией. Все видимы всегда (VD-03), тач-таргет ≥44px (ui/Button).
 *
 * Честность снятия: опубликованное снять нельзя — вместо «Снять» показываем
 * «Открыть пост». Снять можно только то, что ещё не ушло (draft/queued/…/scheduled).
 */
export function AssignmentActions({
  a,
  layout,
  onEdit,
  onCancel,
  onRetry,
  cancellingId,
  retryingId,
}: Props) {
  const editable =
    a.status === "draft" || a.status === "queued" || a.status === "scheduled";
  const cancellable =
    a.status !== "published" &&
    a.status !== "cancelled" &&
    a.status !== "failed";
  const retryable = a.status === "failed" || a.status === "cancelled";

  return (
    <div
      className={
        layout === "row"
          ? "flex flex-wrap gap-2"
          : "flex flex-col gap-2"
      }
    >
      {editable ? (
        <Button variant="secondary" size="sm" onClick={() => onEdit(a)}>
          Изменить
        </Button>
      ) : null}

      {cancellable ? (
        <Button
          variant="danger"
          size="sm"
          onClick={() => onCancel(a)}
          loading={cancellingId === a.id}
        >
          Снять
        </Button>
      ) : null}

      {retryable ? (
        <Button
          variant="primary"
          size="sm"
          onClick={() => onRetry(a)}
          loading={retryingId === a.id}
        >
          Повторить
        </Button>
      ) : null}

      {a.publer_post_url ? (
        <a
          href={a.publer_post_url}
          target="_blank"
          rel="noreferrer noopener"
          className="mono inline-flex min-h-11 items-center justify-center gap-1 rounded-none border border-[var(--gold)] px-3 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--gold)] transition-colors hover:bg-[var(--gold)] hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
        >
          Открыть пост ↗
        </a>
      ) : null}
    </div>
  );
}
