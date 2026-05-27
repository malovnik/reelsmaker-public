import { useUiMode } from "@/contexts";
import { useToast } from "@/contexts";
import type { UiMode } from "@/contexts";

/**
 * Сегмент-контрол режима раскрытия сложности (Пошаговый / Эксперт) — d4 §2.
 * Живёт в шапке справа, глобальный. Обе кнопки всегда подписаны, активная
 * залита --gold с текстом --ink. На <640px подписи сжимаются до «Шаг / Эксп».
 * Состояние и persist — в UiModeContext; смена → подтверждающий тост.
 */

interface SegmentDef {
  mode: UiMode;
  full: string;
  short: string;
  toast: string;
}

const SEGMENTS: SegmentDef[] = [
  {
    mode: "guided",
    full: "Пошаговый",
    short: "Шаг",
    toast: "Режим: Пошаговый. Веду по шагам, лишнее спрятано.",
  },
  {
    mode: "expert",
    full: "Эксперт",
    short: "Эксп",
    toast: "Режим: Эксперт. Показываю все опции сразу.",
  },
];

export function ModeSwitch() {
  const { mode, setMode } = useUiMode();
  const toast = useToast();

  const handle = (next: SegmentDef) => {
    if (next.mode === mode) return;
    setMode(next.mode);
    toast.info(next.toast);
  };

  return (
    <div
      role="group"
      aria-label="Режим интерфейса"
      className="inline-flex items-center rounded-none border border-[color:var(--line)] bg-[color:var(--ink-2)]"
    >
      {SEGMENTS.map((seg) => {
        const active = seg.mode === mode;
        return (
          <button
            key={seg.mode}
            type="button"
            aria-pressed={active}
            onClick={() => handle(seg)}
            className={[
              "mono inline-flex min-h-11 items-center px-3 text-[11px] uppercase tracking-[0.1em] transition-colors duration-150",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--gold)]",
              active
                ? "bg-[color:var(--gold)] text-[color:var(--ink)]"
                : "bg-transparent text-[color:var(--mute-2)] hover:text-[color:var(--paper)]",
            ].join(" ")}
          >
            <span className="hidden sm:inline">{seg.full}</span>
            <span className="sm:hidden">{seg.short}</span>
          </button>
        );
      })}
    </div>
  );
}
