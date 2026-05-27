import type { ReactNode } from "react";
import type { ComposerStrategy } from "@/lib/api";
import { resolveHint, type ControlHintKey } from "@/components/settings-shared";

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
  hintKey,
  children,
}: {
  label: string;
  help?: ReactNode;
  /** Ключ реестра подсказок — добавляет (i)-тултип у метки + инлайн-подсказку. */
  hintKey?: ControlHintKey;
  children: ReactNode;
}) {
  const hint = resolveHint({ hintKey });
  return (
    <div className="flex flex-col gap-2">
      <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        {label}
        {hint.badgeNode}
        {hint.adornment}
      </span>
      {children}
      {hint.inline ? (
        <span className="text-[11px] leading-relaxed text-[color:var(--text-muted)]">
          {hint.inline}
        </span>
      ) : null}
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
  hintKey,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
  hintKey?: ControlHintKey;
}) {
  const hint = resolveHint({ hintKey });
  return (
    <span className="inline-flex items-center gap-1">
      <label
        className={`inline-flex min-h-11 items-center gap-2 py-2 text-xs ${
          disabled
            ? "cursor-not-allowed text-[color:var(--text-disabled)]"
            : "cursor-pointer text-[color:var(--text-secondary)]"
        }`}
        title={disabled ? "В пресете эта опция не настроена" : undefined}
      >
        <input
          type="checkbox"
          checked={checked && !disabled}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="size-4 accent-[color:var(--accent-primary)] disabled:opacity-40"
        />
        {label}
      </label>
      {hint.adornment}
    </span>
  );
}

export function ToggleRow({
  id,
  label,
  hint,
  hintKey,
  checked,
  onChange,
  disabled,
  disabledReason,
}: {
  id: string;
  label: string;
  hint: string;
  hintKey?: ControlHintKey;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const effective = disabled ? false : checked;
  const resolved = resolveHint({ hintKey });
  const inline = resolved.inline || hint;
  return (
    <div
      className={`flex items-start justify-between gap-4 ${disabled ? "opacity-60" : ""}`}
    >
      <div className="flex flex-1 flex-col">
        <span className="flex items-center gap-1.5">
          <label
            htmlFor={id}
            className="text-sm text-[color:var(--text-primary)]"
          >
            {label}
          </label>
          {resolved.badgeNode}
          {resolved.adornment}
        </span>
        <p className="mt-1 text-xs text-[color:var(--text-muted)]">
          {disabled && disabledReason ? disabledReason : inline}
        </p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={effective}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="group/toggle relative flex size-11 shrink-0 items-center justify-center rounded-full disabled:cursor-not-allowed"
      >
        <span
          className={[
            "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
            effective
              ? "bg-[color:var(--accent-primary)]"
              : "bg-[color:var(--border-default)]",
          ].join(" ")}
          aria-hidden="true"
        >
          <span
            className={[
              "inline-block size-5 transform rounded-full bg-[color:var(--surface-raised)] shadow-[var(--shadow-xs)] transition-transform",
              effective ? "translate-x-[1.375rem]" : "translate-x-0.5",
            ].join(" ")}
          />
        </span>
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
  const hint = resolveHint({ hintKey: "composer_strategy_override" });
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[color:var(--line-soft)] bg-[color:var(--ink-2)] p-4">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[color:var(--text-muted)]">
        Стиль монтажа
        {hint.adornment}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {COMPOSER_STRATEGY_OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className="flex min-h-11 cursor-pointer items-start gap-2 rounded-md border border-[color:var(--line-soft)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm hover:border-[color:var(--line)] has-[:checked]:border-[color:var(--gold)] has-[:checked]:bg-[color:var(--ink-3)]"
          >
            <input
              type="radio"
              name="composer_strategy"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className="mt-0.5 accent-[color:var(--accent-primary)]"
            />
            <span>
              <span className="block font-medium text-[color:var(--text-primary)]">
                {opt.title}
              </span>
              <span className="text-xs leading-snug text-[color:var(--text-muted)]">
                {opt.hint}
              </span>
            </span>
          </label>
        ))}
      </div>
      <p className="pt-1 text-[11px] leading-relaxed text-[color:var(--text-muted)]">
        Определяет, как композитор собирает рилсы из отобранных моментов. Любой
        вариант кроме «Авто» переопределяет решение робота-монтажёра.
      </p>
    </div>
  );
}
