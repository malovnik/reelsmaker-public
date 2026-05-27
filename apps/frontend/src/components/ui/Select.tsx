import { forwardRef } from "react";
import type { ReactNode, SelectHTMLAttributes } from "react";
import { cn } from "./cn";
import { Field } from "./Field";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** Опции списком. Если нужны группы — передавайте children через optionsSlot. */
  options?: SelectOption[];
  /** Плейсхолдер-опция (disabled, value=""). */
  placeholder?: string;
  /** Произвольное содержимое <select> (optgroup и т.п.) вместо options. */
  optionsSlot?: ReactNode;
}

const selectBase =
  "w-full appearance-none rounded-none border bg-[var(--ink)] text-[var(--paper)] " +
  "border-[var(--line)] py-[14px] pl-[18px] pr-10 text-[0.9375rem] leading-snug " +
  "transition-colors duration-200 " +
  "hover:border-[var(--mute)] " +
  "focus:border-[var(--gold)] focus:outline-none " +
  "disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-[invalid=true]:border-[var(--danger)] " +
  // стрелка через background — токенный цвет
  "bg-[length:10px] bg-[right_1rem_center] bg-no-repeat " +
  "[background-image:url(\"data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2010%206'%3E%3Cpath%20d='M1%201l4%204%204-4'%20stroke='%238A8278'%20stroke-width='1.5'%20fill='none'/%3E%3C/svg%3E\")]";

/**
 * Стилизованный селект. Нативный <select> (доступность, мобильный picker),
 * кастомная стрелка, прямые углы, focus → золото.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, required, className, id, options, placeholder, optionsSlot, ...rest },
  ref,
) {
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      {({ id: fieldId, describedBy, invalid }) => (
        <select
          ref={ref}
          id={fieldId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(selectBase, className)}
          {...rest}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {optionsSlot ??
            options?.map((opt) => (
              <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                {opt.label}
              </option>
            ))}
        </select>
      )}
    </Field>
  );
});
