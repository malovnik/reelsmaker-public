import { Link } from "react-router-dom";
import { usePathname } from "@/lib/router-compat";
import { useMemo } from "react";

interface Crumb {
  label: string;
  href?: string;
}

const SEGMENT_LABELS: Record<string, string> = {
  "": "Студия",
  jobs: "Библиотека",
  settings: "Настройки",
  models: "Модели",
  performance: "Производительность",
  "post-production": "Пост-продакшн",
  prompts: "Промпты",
  subtitles: "Субтитры",
  profiles: "Профили",
  tinder: "Tinder",
};

function humanizeSegment(seg: string): string {
  if (seg in SEGMENT_LABELS) return SEGMENT_LABELS[seg];
  if (/^[0-9a-f]{8}-/i.test(seg)) return `${seg.slice(0, 8)}…`;
  return seg;
}

interface Props {
  /**
   * Открывает mobile-drawer с навигацией. На viewport ≥1024px кнопка
   * скрыта, рейл всегда в потоке.
   */
  onOpenNav?: () => void;
}

export function TopBar({ onOpenNav }: Props) {
  const pathname = usePathname();

  const crumbs = useMemo<Crumb[]>(() => {
    if (pathname === "/") {
      return [{ label: "Нарезки" }];
    }
    const segments = pathname.split("/").filter(Boolean);
    const result: Crumb[] = [{ label: "Нарезки", href: "/" }];
    let acc = "";
    segments.forEach((seg, idx) => {
      acc += `/${seg}`;
      const isLast = idx === segments.length - 1;
      result.push({
        label: humanizeSegment(seg),
        href: isLast ? undefined : acc,
      });
    });
    return result;
  }, [pathname]);

  return (
    <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-3 border-b border-[color:var(--line-soft)] bg-[color:var(--ink)]/85 px-4 backdrop-blur-md sm:gap-5 sm:px-6 lg:px-8">
      {/* Burger — открывает mobile drawer. Скрыт на desktop. */}
      <button
        type="button"
        onClick={onOpenNav}
        aria-label="Открыть навигацию"
        className="-ml-1 inline-flex size-9 items-center justify-center rounded-md text-[color:var(--mute-2)] transition-colors hover:bg-[color:var(--ink-2)] hover:text-[color:var(--paper)] lg:hidden"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      <nav
        aria-label="Хлебные крошки"
        className="flex min-w-0 flex-1 items-center gap-2.5 overflow-x-auto text-sm"
      >
        {crumbs.map((c, idx) => {
          const last = idx === crumbs.length - 1;
          return (
            <span key={`${c.label}-${idx}`} className="flex shrink-0 items-center gap-2.5">
              {idx > 0 ? (
                <span className="mono mute text-[10px]" aria-hidden="true">
                  /
                </span>
              ) : null}
              {c.href && !last ? (
                <Link
                  to={c.href}
                  className="text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
                >
                  {c.label}
                </Link>
              ) : (
                <span
                  className={
                    last
                      ? "text-[color:var(--paper)]"
                      : "text-[color:var(--mute-2)]"
                  }
                >
                  {c.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-3">
        <div
          className="mono hidden min-w-[420px] items-center gap-2.5 rounded-md border border-[color:var(--line-soft)] bg-[color:var(--ink-2)] px-3.5 py-2 text-[12px] text-[color:var(--mute-2)] xl:flex"
          aria-label="Поиск по проектам"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span className="flex-1 text-[12px]">Найти проект, клип, момент…</span>
          <span className="kbd">⌘K</span>
        </div>
      </div>
    </header>
  );
}
