import type { ReactNode } from "react";
import { resolveHint, type HintSource } from "./hintAdornment";

export interface GroupProps extends HintSource {
  title: string;
  /** Honesty-бейдж группы (например, opt-in на всём Vision). */
  children: ReactNode;
}

/**
 * Карточка-группа связанных настроек (Эксперт-студия §3, §6).
 * Sumi-подложка на Kuro, прямые углы, заголовок Noto Serif JP. Внутри плотно
 * (gap-3), между группами — воздух задаёт родитель. Опц. `hintKey` вешает
 * (i)-подсказку и honesty-бейдж на заголовок группы.
 */
export function Group({ title, hintKey, hint, children }: GroupProps) {
  const { adornment, badgeNode } = resolveHint({ hintKey, hint });
  return (
    <section className="rounded-none border border-[var(--line)] bg-[var(--ink-2)] p-5 md:p-6">
      <header className="mb-4 flex items-center gap-2 border-b border-[var(--line)] pb-3">
        <h3 className="font-[family-name:var(--font-serif)] text-[0.9375rem] font-bold uppercase tracking-[0.08em] text-[var(--paper)]">
          {title}
        </h3>
        {badgeNode}
        {adornment}
      </header>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}
