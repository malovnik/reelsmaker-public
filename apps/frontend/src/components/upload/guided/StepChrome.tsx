/**
 * Общая «обвязка» шага Пошагового режима: сквозной прогресс-индикатор сверху
 * и липкая навигация назад/далее снизу. Один компонент на всех экранах
 * настройки (S1–S6) — даёт единый ритм и ответ на «где я и сколько осталось».
 *
 * Брендбук: латунь на чёрном, прямые углы, mono-мета, Noto Serif заголовки.
 */
import type { ReactNode } from "react";
import { cn } from "@/components/ui";

/** Шаги настройки, у которых есть прогресс-полоса (S1–S6). */
export const SETUP_STEP_LABELS = [
  "Проект",
  "Видео",
  "Вид",
  "Субтитры",
  "Обработка",
  "Модели",
] as const;

export const SETUP_STEP_COUNT = SETUP_STEP_LABELS.length;

interface ProgressBarProps {
  /** Номер текущего шага настройки, 1..6. */
  current: number;
  /** Заголовок секции слева от счётчика. */
  caption?: string;
  /** Прыжок на пройденный шаг по клику на метку. */
  onJump?: (step: number) => void;
}

/** Прогресс-полоса настройки: «ШАГ N / 6» + заполнение + кликабельные метки. */
export function SetupProgress({
  current,
  caption = "Настройка",
  onJump,
}: ProgressBarProps) {
  const pct = (current / SETUP_STEP_COUNT) * 100;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.16em] text-[var(--mute)]">
          {caption}
        </span>
        <span className="font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.16em] text-[var(--gold)]">
          Шаг {current} / {SETUP_STEP_COUNT}
        </span>
      </div>
      <div className="h-1 w-full bg-[var(--ink-3)]">
        <div
          className="h-full bg-[var(--gold)] transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {SETUP_STEP_LABELS.map((label, i) => {
          const step = i + 1;
          const done = step < current;
          const active = step === current;
          const clickable = step <= current && onJump;
          return (
            <button
              key={label}
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onJump?.(step)}
              className={cn(
                "font-[family-name:var(--font-mono)] text-[0.625rem] uppercase tracking-[0.12em] transition-colors",
                active && "text-[var(--gold)]",
                done && "text-[var(--mute-2)] hover:text-[var(--gold)]",
                !active && !done && "text-[var(--mute)] opacity-50",
                clickable && "cursor-pointer",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface StepShellProps {
  tag: string;
  title: string;
  /** Подзаголовок-объяснение (Manrope, mute). */
  lead?: ReactNode;
  /** Прогресс-полоса сверху (S1–S6). На S7/S8/S9+ не передаётся. */
  progress?: ReactNode;
  children: ReactNode;
  /** Кнопки навигации снизу (BackNext или произвольный узел). */
  footer?: ReactNode;
}

/** Каркас одного экрана-шага: tag + заголовок + lead + контент + липкий футер. */
export function StepShell({
  tag,
  title,
  lead,
  progress,
  children,
  footer,
}: StepShellProps) {
  return (
    <div className="fade-in flex flex-col gap-8">
      {progress}
      <div className="flex flex-col gap-2">
        <span className="font-[family-name:var(--font-pixel)] text-[0.625rem] uppercase tracking-[0.1em] text-[var(--copper)]">
          {tag}
        </span>
        <h2 className="font-[family-name:var(--font-display)] text-2xl leading-tight text-[var(--paper)] sm:text-[2rem]">
          {title}
        </h2>
        {lead && (
          <p className="max-w-[52ch] text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
            {lead}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-5">{children}</div>
      {footer}
    </div>
  );
}

interface BackNextProps {
  onBack?: () => void;
  onNext?: () => void;
  backLabel?: string;
  nextLabel?: string;
  nextDisabled?: boolean;
  /** Подсказка под заблокированной кнопкой «Далее» (например, «нужен файл»). */
  nextHint?: string;
}

/**
 * Липкая нижняя навигация шага. На мобайле прилипает к низу экрана, на десктопе
 * остаётся в потоке. Кнопка «Далее» — primary (золотая обводка → заливка).
 */
export function BackNext({
  onBack,
  onNext,
  backLabel = "← Назад",
  nextLabel = "Далее →",
  nextDisabled,
  nextHint,
}: BackNextProps) {
  return (
    <div className="sticky bottom-0 -mx-6 mt-4 flex flex-col gap-1 border-t border-[var(--line)] bg-[var(--ink-2)] px-6 py-4 sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:px-0 sm:py-0">
      <div className="flex items-center justify-between gap-3">
        {onBack ? (
          <button type="button" className="btn btn-ghost" onClick={onBack}>
            {backLabel}
          </button>
        ) : (
          <span />
        )}
        {onNext && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={onNext}
            disabled={nextDisabled}
            aria-disabled={nextDisabled}
          >
            {nextLabel}
          </button>
        )}
      </div>
      {nextDisabled && nextHint && (
        <span className="text-right text-[0.75rem] text-[var(--mute)]">
          {nextHint}
        </span>
      )}
    </div>
  );
}
