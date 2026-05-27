
export interface SelectRowProps<T extends number | string> {
  id: string;
  label: string;
  hint: string;
  value: T;
  options: { value: T; label: string }[];
  disabled?: boolean;
  onChange: (value: T) => void;
}

/**
 * Select-элемент с типизированными значениями (number | string).
 *
 * Shared settings primitive. Используется как drop-in замена локальным
 * определениям в *SettingsClient.tsx (план Phase 8.3-8.6 декомпозиции).
 */
export function SelectRow<T extends number | string>({
  id,
  label,
  hint,
  value,
  options,
  disabled,
  onChange,
}: SelectRowProps<T>) {
  return (
    <div className={disabled ? "opacity-50" : undefined}>
      <label htmlFor={id} className="text-sm text-[color:var(--text-primary)]">
        {label}
      </label>
      <select
        id={id}
        value={String(value)}
        disabled={disabled}
        aria-describedby={`${id}-hint`}
        onChange={(e) => {
          const raw = e.target.value;
          const matched = options.find((opt) => String(opt.value) === raw);
          if (matched) onChange(matched.value);
        }}
        className="mt-2 block w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus-visible:border-[color:var(--accent-primary)] focus-visible:ring-2 focus-visible:ring-[color:var(--accent-primary-subtle)] disabled:cursor-not-allowed"
      >
        {options.map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
      <p
        id={`${id}-hint`}
        className="mt-1.5 text-xs text-[color:var(--text-muted)]"
      >
        {hint}
      </p>
    </div>
  );
}
