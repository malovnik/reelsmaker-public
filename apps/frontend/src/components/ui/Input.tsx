import { forwardRef } from "react";
import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cn } from "./cn";
import { Field } from "./Field";

const controlBase =
  "w-full rounded-none border bg-[var(--ink)] text-[var(--paper)] " +
  "border-[var(--line)] px-[18px] py-[14px] text-[0.9375rem] leading-snug " +
  "placeholder:text-[var(--mute)] " +
  "transition-colors duration-200 " +
  "hover:border-[var(--mute)] " +
  "focus:border-[var(--gold)] focus:outline-none " +
  "disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-[invalid=true]:border-[var(--danger)]";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

/**
 * Текстовое поле по брендбуку: bg #1A1A1A-слой, Hai-бордер, focus → золото,
 * прямые углы, padding 14px/18px. Метка/hint/ошибка через Field.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, required, className, id, ...rest },
  ref,
) {
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      {({ id: fieldId, describedBy, invalid }) => (
        <input
          ref={ref}
          id={fieldId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(controlBase, className)}
          {...rest}
        />
      )}
    </Field>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

/** Многострочное поле в той же стилистике, что и Input. */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, required, className, id, rows = 4, ...rest },
  ref,
) {
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      {({ id: fieldId, describedBy, invalid }) => (
        <textarea
          ref={ref}
          id={fieldId}
          rows={rows}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(controlBase, "resize-y", className)}
          {...rest}
        />
      )}
    </Field>
  );
});
