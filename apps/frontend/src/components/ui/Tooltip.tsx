import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "./cn";
import { Badge, HONESTY_LABELS } from "./Badge";
import type { HonestyBadge } from "./Badge";

export type TooltipSide = "left" | "right" | "top" | "bottom";

export interface TooltipProps {
  /** ЧТО ДЕЛАЕТ — 1 строка. Обязательно. */
  what: string;
  /** ЭФФЕКТ на скорость/качество/стоимость/кадр. Обязательно. */
  effect: string;
  /** РЕКОМЕНДАЦИЯ «Оставьте X для Y». Обязательно. */
  advise: string;
  /** Бейдж честности (опц.). */
  badge?: HonestyBadge;
  /** Кастомный текст бейджа (по умолчанию — из HONESTY_LABELS). */
  badgeLabel?: ReactNode;
  /** Предпочтительная сторона (студия: left). Авто-флип если не помещается. */
  side?: TooltipSide;
  /**
   * Всегда-видимая инлайн-подсказка под триггером (1-я строка `what` серым).
   * Не floating — для «подсказки напротив каждого контрола».
   */
  inline?: boolean;
  /** Триггер: оборачиваемый контрол. Если не передан — рендерит иконку (i). */
  children?: ReactNode;
  className?: string;
}

const FLIP_ORDER: Record<TooltipSide, TooltipSide[]> = {
  left: ["left", "right", "top", "bottom"],
  right: ["right", "left", "top", "bottom"],
  top: ["top", "bottom", "left", "right"],
  bottom: ["bottom", "top", "left", "right"],
};

const GAP = 8;
const MAX_W = 280;

function isCoarsePointer() {
  return typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
}

/**
 * Двухуровневая подсказка. Inline-hint (опц., всегда видим) + full-tooltip
 * (hover 150ms / focus / tap-(i) 44px) из 3 частей what/effect/advise + бейдж.
 * Мультимодальность мышь/клавиатура/тач, aria-describedby, авто-флип позиции.
 * На coarse-pointer (тач) — раскрывается как блок под контролом (не floating).
 */
export function Tooltip({
  what,
  effect,
  advise,
  badge,
  badgeLabel,
  side = "left",
  inline,
  children,
  className,
}: TooltipProps) {
  const id = useId();
  const tipId = `tip-${id}`;
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; side: TooltipSide } | null>(
    null,
  );
  const [coarse, setCoarse] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setCoarse(isCoarsePointer());
  }, []);

  const show = useCallback((delay = 0) => {
    window.clearTimeout(hoverTimer.current);
    if (delay) {
      hoverTimer.current = window.setTimeout(() => setOpen(true), delay);
    } else {
      setOpen(true);
    }
  }, []);

  const hide = useCallback(() => {
    window.clearTimeout(hoverTimer.current);
    setOpen(false);
  }, []);

  useEffect(() => () => window.clearTimeout(hoverTimer.current), []);

  // Esc закрывает
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, hide]);

  // Позиционирование floating-карточки с авто-флипом (только не-coarse)
  useLayoutEffect(() => {
    if (!open || coarse) return;
    const trigger = triggerRef.current;
    const tip = tipRef.current;
    if (!trigger || !tip) return;

    const t = trigger.getBoundingClientRect();
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const place = (s: TooltipSide) => {
      switch (s) {
        case "left":
          return { top: t.top + t.height / 2 - th / 2, left: t.left - tw - GAP };
        case "right":
          return { top: t.top + t.height / 2 - th / 2, left: t.right + GAP };
        case "top":
          return { top: t.top - th - GAP, left: t.left + t.width / 2 - tw / 2 };
        case "bottom":
          return { top: t.bottom + GAP, left: t.left + t.width / 2 - tw / 2 };
      }
    };
    const fits = (p: { top: number; left: number }) =>
      p.left >= 4 && p.left + tw <= vw - 4 && p.top >= 4 && p.top + th <= vh - 4;

    let chosen = FLIP_ORDER[side][0];
    let pos = place(chosen);
    for (const s of FLIP_ORDER[side]) {
      const p = place(s);
      if (fits(p)) {
        chosen = s;
        pos = p;
        break;
      }
    }
    // clamp в вьюпорт
    pos.left = Math.max(4, Math.min(pos.left, vw - tw - 4));
    pos.top = Math.max(4, Math.min(pos.top, vh - th - 4));
    setCoords({ ...pos, side: chosen });
  }, [open, coarse, side, what, effect, advise]);

  const resolvedBadgeLabel = badge ? (badgeLabel ?? HONESTY_LABELS[badge]) : null;

  const card = (
    <div
      ref={tipRef}
      id={tipId}
      role="tooltip"
      style={coarse ? undefined : { top: coords?.top ?? -9999, left: coords?.left ?? -9999, maxWidth: MAX_W }}
      className={cn(
        "rounded-none border border-[var(--line)] border-l-2 border-l-[var(--gold)] bg-[var(--ink-2)] px-4 py-3",
        coarse
          ? "mt-1 w-full"
          : "fixed z-[300] motion-safe:animate-[fade-in_0.15s_ease-out]",
      )}
    >
      <p className="text-[0.875rem] font-semibold leading-snug text-[var(--paper)]">{what}</p>
      <p className="mt-1.5 text-[0.8125rem] leading-snug text-[var(--mute)]">{effect}</p>
      <p className="mt-1.5 text-[0.8125rem] leading-snug text-[var(--paper)] before:text-[var(--copper,var(--ember))] before:content-['→_']">
        {advise}
      </p>
      {badge && (
        <div className="mt-2.5">
          <Badge variant={badge} pixel>
            {resolvedBadgeLabel}
          </Badge>
        </div>
      )}
    </div>
  );

  return (
    <span className={cn("inline-flex flex-col", className)}>
      <span className="inline-flex items-center gap-1.5">
        <span
          ref={triggerRef}
          aria-describedby={open ? tipId : undefined}
          onMouseEnter={coarse ? undefined : () => show(150)}
          onMouseLeave={coarse ? undefined : hide}
          onFocus={coarse ? undefined : () => show(0)}
          onBlur={coarse ? undefined : hide}
          className="inline-flex"
        >
          {children ?? (
            <button
              type="button"
              aria-label="Подсказка"
              aria-expanded={coarse ? open : undefined}
              aria-describedby={open ? tipId : undefined}
              onClick={coarse ? () => setOpen((v) => !v) : undefined}
              onMouseEnter={coarse ? undefined : () => show(150)}
              onMouseLeave={coarse ? undefined : hide}
              onFocus={coarse ? undefined : () => show(0)}
              onBlur={coarse ? undefined : hide}
              className="inline-flex size-11 items-center justify-center rounded-none text-[var(--mute-2)] transition-colors hover:text-[var(--gold)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 7v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                <circle cx="8" cy="4.5" r="0.9" fill="currentColor" />
              </svg>
            </button>
          )}
        </span>
        {/* (i)-триггер для тач, когда триггером выступает контрол (не сама иконка) */}
        {coarse && children && (
          <button
            type="button"
            aria-label="Подсказка"
            aria-expanded={open}
            aria-describedby={open ? tipId : undefined}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-none text-[var(--mute-2)] transition-colors hover:text-[var(--gold)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 7v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="8" cy="4.5" r="0.9" fill="currentColor" />
            </svg>
          </button>
        )}
      </span>

      {/* Inline-hint: всегда видимая первая строка */}
      {inline && (
        <span className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">{what}</span>
      )}

      {/* Full-tooltip */}
      {open && (coarse ? card : createPortal(card, document.body))}
    </span>
  );
}
