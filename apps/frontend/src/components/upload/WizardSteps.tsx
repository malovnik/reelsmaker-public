import type { ReactNode } from "react";
import type { ComposerStrategy } from "@/lib/api";

export function Step({
  index,
  title,
  hint,
  children,
}: {
  index: number;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline gap-3">
        <span
          className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-sunken)] font-mono text-[11px] font-medium text-[color:var(--text-secondary)]"
          aria-hidden="true"
        >
          {index}
        </span>
        <h3 className="text-sm font-semibold tracking-tight text-[color:var(--text-primary)]">
          {title}
        </h3>
        {hint ? (
          <span className="text-[11px] text-[color:var(--text-muted)]">
            {hint}
          </span>
        ) : null}
      </div>
      <div className="pl-9">{children}</div>
    </section>
  );
}

export function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        {label}
      </span>
      {children}
      {help ? (
        <span className="text-[11px] leading-relaxed text-[color:var(--text-muted)]">
          {help}
        </span>
      ) : null}
    </div>
  );
}

export function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (next: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function OverrideCheckbox({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label
      className={`inline-flex items-center gap-2 text-xs ${
        disabled
          ? "cursor-not-allowed text-[color:var(--text-disabled)]"
          : "cursor-pointer text-[color:var(--text-secondary)]"
      }`}
      title={
        disabled
          ? "В пресете эта опция не настроена"
          : "Применить эту часть пресета к рилсу"
      }
    >
      <input
        type="checkbox"
        checked={checked && !disabled}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="size-3.5 accent-[color:var(--accent-primary)] disabled:opacity-40"
      />
      {label}
    </label>
  );
}

export function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled,
  disabledReason,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const effective = disabled ? false : checked;
  return (
    <div
      className={`flex items-start justify-between gap-4 ${disabled ? "opacity-60" : ""}`}
    >
      <div className="flex flex-1 flex-col">
        <label
          htmlFor={id}
          className="text-sm text-[color:var(--text-primary)]"
        >
          {label}
        </label>
        <p className="mt-1 text-xs text-[color:var(--text-muted)]">
          {disabled && disabledReason ? disabledReason : hint}
        </p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={effective}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={[
          "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed",
          effective
            ? "bg-[color:var(--accent-primary)]"
            : "bg-[color:var(--border-default)]",
        ].join(" ")}
      >
        <span
          className={[
            "inline-block size-5 transform rounded-full bg-white transition-transform",
            effective ? "translate-x-[1.375rem]" : "translate-x-0.5",
          ].join(" ")}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}

const COMPOSER_STRATEGY_OPTIONS: Array<{
  value: ComposerStrategy;
  title: string;
  hint: string;
}> = [
  {
    value: "auto",
    title: "Автоматически",
    hint: "Робот-монтажёр сам подберёт стратегию по характеру аудио.",
  },
  {
    value: "tight_context",
    title: "Плотный контекст",
    hint:
      "Рилсы собираются только из близких по времени фрагментов. Минимум" +
      " cross-context рисков, но меньше тематической широты.",
  },
  {
    value: "balanced",
    title: "Сбалансированно",
    hint:
      "Смесь chronological и thematic candidates. Универсальный режим для" +
      " подкастов и интервью.",
  },
  {
    value: "thematic_free",
    title: "Свободная тематика",
    hint:
      "Активно смешивает далёкие по времени, но близкие по смыслу фрагменты." +
      " Может дать необычные склейки — обязательно проверь результат.",
  },
];

export function ComposerStrategyBlock({
  value,
  onChange,
}: {
  value: ComposerStrategy;
  onChange: (next: ComposerStrategy) => void;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[color:var(--line-soft)] bg-[color:var(--ink-2)] p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-stone-500">
        Стиль монтажа (composer strategy)
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {COMPOSER_STRATEGY_OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className="flex cursor-pointer items-start gap-2 rounded-md border border-[color:var(--line-soft)] bg-white px-3 py-2 text-sm hover:border-[color:var(--line)] has-[:checked]:border-[color:var(--gold)] has-[:checked]:bg-[color:var(--ink-3)]"
          >
            <input
              type="radio"
              name="composer_strategy"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className="mt-0.5"
            />
            <span>
              <span className="block font-medium text-stone-900">
                {opt.title}
              </span>
              <span className="text-xs leading-snug text-stone-500">
                {opt.hint}
              </span>
            </span>
          </label>
        ))}
      </div>
      <p className="pt-1 text-[11px] leading-relaxed text-stone-500">
        Plotline-стиль: определяет, как композитор собирает рилсы из ranked-
        сегментов. Не-авто принудительно переопределяет решение advisor&apos;а.
      </p>
    </div>
  );
}
