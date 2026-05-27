import { useId } from "react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export interface FieldProps {
  /** Видимая метка поля. */
  label?: ReactNode;
  /** Всегда-видимая инлайн-подсказка под меткой (серым). */
  hint?: ReactNode;
  /** Текст ошибки — заменяет hint, окрашен в --danger. */
  error?: ReactNode;
  /** Отметить поле обязательным (золотая звёздочка). */
  required?: boolean;
  /** id поля для связки label/aria. Если не передан — генерируется. */
  htmlFor?: string;
  className?: string;
  children: (ctx: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}

/**
 * Обёртка поля: метка + инлайн-hint + ошибка с правильной a11y-связкой
 * (aria-describedby / aria-invalid). children — render-prop, получает id и
 * describedBy для нативного контрола.
 */
export function Field({
  label,
  hint,
  error,
  required,
  htmlFor,
  className,
  children,
}: FieldProps) {
  const generatedId = useId();
  const id = htmlFor ?? generatedId;
  const descId = `${id}-desc`;
  const invalid = Boolean(error);
  const describedBy = error || hint ? descId : undefined;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label
          htmlFor={id}
          className="font-[family-name:var(--font-mono)] text-[0.75rem] uppercase tracking-[0.1em] text-[var(--mute-2)]"
        >
          {label}
          {required && <span className="ml-1 text-[var(--gold)]">*</span>}
        </label>
      )}

      {children({ id, describedBy, invalid })}

      {(error || hint) && (
        <p
          id={descId}
          className={cn(
            "text-[0.8125rem] leading-snug",
            error ? "text-[var(--danger)]" : "text-[var(--mute)]",
          )}
        >
          {error ?? hint}
        </p>
      )}
    </div>
  );
}
