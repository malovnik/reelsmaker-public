import type { HintSource } from "./hintAdornment";
import { resolveHint } from "./hintAdornment";

export interface SelectRowProps<T extends number | string> extends HintSource {
  id: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  disabled?: boolean;
  onChange: (value: T) => void;
}

const selectClass =
  "mt-2 block w-full appearance-none rounded-none border border-[var(--line)] bg-[var(--ink)] " +
  "py-[14px] pl-[18px] pr-10 text-[0.9375rem] leading-snug text-[var(--paper)] outline-none " +
  "transition-colors hover:border-[var(--mute)] focus:border-[var(--gold)] disabled:cursor-not-allowed " +
  "bg-[length:10px] bg-[right_1rem_center] bg-no-repeat " +
  "[background-image:url(\"data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2010%206'%3E%3Cpath%20d='M1%201l4%204%204-4'%20stroke='%238A8278'%20stroke-width='1.5'%20fill='none'/%3E%3C/svg%3E\")]";

/**
 * Селект с обязательной подсказкой (Эксперт-студия §2). Прямые углы,
 * кастомная стрелка, фокус → золото. `hintKey` → триплет из реестра.
 */
export function SelectRow<T extends number | string>({
  id,
  label,
  hintKey,
  hint,
  value,
  options,
  disabled,
  onChange,
}: SelectRowProps<T>) {
  const { inline, adornment, badgeNode } = resolveHint({ hintKey, hint });
  const hintId = `${id}-hint`;
  return (
    <div className={disabled ? "opacity-50" : undefined}>
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="text-[0.9375rem] font-medium text-[var(--paper)]">
          {label}
        </label>
        {badgeNode}
        {adornment}
      </div>
      <select
        id={id}
        value={String(value)}
        disabled={disabled}
        aria-describedby={hintId}
        onChange={(e) => {
          const raw = e.target.value;
          const matched = options.find((opt) => String(opt.value) === raw);
          if (matched) onChange(matched.value);
        }}
        className={selectClass}
      >
        {options.map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
      <p id={hintId} className="mt-1.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
        {inline}
      </p>
    </div>
  );
}
