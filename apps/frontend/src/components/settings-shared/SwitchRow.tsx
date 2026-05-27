
export interface SwitchRowProps {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/**
 * Accessible toggle-switch с меткой и подсказкой.
 *
 * Shared settings primitive. Используется как drop-in замена локальным
 * определениям в *SettingsClient.tsx (план Phase 8.3-8.6 декомпозиции).
 */
export function SwitchRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: SwitchRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-1 flex-col">
        <label htmlFor={id} className="text-sm text-[color:var(--text-primary)]">
          {label}
        </label>
        <p
          id={`${id}-hint`}
          className="mt-1 text-xs text-[color:var(--text-muted)]"
        >
          {hint}
        </p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={`${id}-hint`}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--accent-primary)] ${
          checked
            ? "bg-[color:var(--accent-primary)]"
            : "bg-[color:var(--border-default)]"
        }`}
      >
        <span
          className={`inline-block size-5 transform rounded-full bg-white transition-transform ${
            checked ? "translate-x-[1.375rem]" : "translate-x-0.5"
          }`}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}
