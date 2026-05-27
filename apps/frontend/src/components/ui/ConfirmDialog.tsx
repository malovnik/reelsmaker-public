import { useRef } from "react";
import type { ReactNode } from "react";
import { Modal } from "./Modal";
import { Button } from "./Button";

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  /** Тело: что именно произойдёт и обратимо ли. */
  description: ReactNode;
  /** Текст кнопки подтверждения. */
  confirmLabel?: string;
  /** Текст кнопки отмены. */
  cancelLabel?: string;
  /** Деструктивное действие → danger-стиль + точечный верхний бордер. */
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Презентационный диалог подтверждения на базе Modal (alertdialog, фокус-трап,
 * Esc=отмена). Автофокус на «Отмена» — деструктивная кнопка не в фокусе.
 * Промис-хук useConfirm подключит другой агент.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  destructive,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <Modal
      open={open}
      onClose={onCancel}
      role="alertdialog"
      size="sm"
      danger={destructive}
      closeOnOverlay={false}
      initialFocusRef={cancelRef}
      title={title}
      footer={
        <>
          <Button ref={cancelRef} variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">{description}</p>
    </Modal>
  );
}
