import { Button } from "@/components/ui";
import type { ButtonProps } from "@/components/ui";
import { resolveHint, type HintSource } from "./hintAdornment";

export interface ActionButtonProps extends HintSource {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  type?: "button" | "submit";
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}

/**
 * Кнопка-действие с обязательной подсказкой (Эксперт-студия §2.4 п.4).
 * Для действий `advise` = что произойдёт и обратимо ли. (i)-тултип + бейдж
 * рендерятся рядом с кнопкой; покрытие гарантировано тем же `hintKey`.
 */
export function ActionButton({
  children,
  onClick,
  variant = "secondary",
  size = "sm",
  type = "button",
  disabled,
  loading,
  className,
  hintKey,
  hint,
}: ActionButtonProps) {
  const { adornment } = resolveHint({ hintKey, hint });
  return (
    <span className="inline-flex items-center gap-1.5">
      <Button
        type={type}
        variant={variant}
        size={size}
        disabled={disabled}
        loading={loading}
        onClick={onClick}
        className={className}
      >
        {children}
      </Button>
      {adornment}
    </span>
  );
}
