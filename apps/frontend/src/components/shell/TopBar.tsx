import { Link } from "react-router-dom";
import { usePathname } from "@/lib/router-compat";
import { useMemo } from "react";
import {
  NAV_ZONES,
  SETTINGS_SECTIONS,
  isZoneActive,
} from "@/lib/nav/routes";
import { ModeSwitch } from "./ModeSwitch";
import { HealthIndicator } from "./HealthIndicator";

interface Crumb {
  label: string;
  href?: string;
}

/**
 * Метки сегментов пути для крошек. Источник правды — единый словарь
 * (NAV_ZONES + SETTINGS_SECTIONS); здесь — только вложенные сегменты, которых
 * нет в словаре (детальные экраны проектов/планировщика).
 */
const EXTRA_SEGMENT_LABELS: Record<string, string> = {
  jobs: "Библиотека",
  reels: "Клипы",
  tinder: "Отбор",
  folder: "Папка",
  accounts: "Аккаунты",
  campaigns: "Кампании",
  presets: "Пресеты",
  new: "Создать",
};

/** label → href из словаря по первому сегменту пути. */
const SEGMENT_FROM_DICTIONARY: Record<string, string> = {
  ...Object.fromEntries(
    SETTINGS_SECTIONS.map((s) => [s.href.split("/").pop() as string, s.label]),
  ),
};

function humanizeSegment(seg: string): string {
  if (seg in EXTRA_SEGMENT_LABELS) return EXTRA_SEGMENT_LABELS[seg];
  if (seg in SEGMENT_FROM_DICTIONARY) return SEGMENT_FROM_DICTIONARY[seg];
  if (/^[0-9a-f]{8}-/i.test(seg)) return `${seg.slice(0, 8)}…`;
  if (/^\d+$/.test(seg)) return `#${seg}`;
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
    // Стартовая крошка — активная зона из словаря (Студия по умолчанию).
    const zone =
      NAV_ZONES.find((z) => isZoneActive(z, pathname)) ?? NAV_ZONES[0];

    if (pathname === "/" || pathname === zone.href) {
      return [{ label: zone.label }];
    }

    const result: Crumb[] = [{ label: zone.label, href: zone.href }];
    const segments = pathname.split("/").filter(Boolean);
    let acc = "";
    segments.forEach((seg, idx) => {
      acc += `/${seg}`;
      // пропускаем сегмент, совпавший с уже добавленным href зоны
      if (acc === zone.href) return;
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
        className="-ml-1 inline-flex size-11 items-center justify-center rounded-none text-[color:var(--mute-2)] transition-colors hover:bg-[color:var(--ink-2)] hover:text-[color:var(--paper)] lg:hidden"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Лого — только на mobile (на desktop живёт в шапке рейла). */}
      <Link
        to="/"
        aria-label="Reelibra — на главную"
        className="flex shrink-0 items-center gap-2 lg:hidden"
      >
        <span className="display-serif text-[1.25rem] font-semibold leading-none tracking-[-0.025em] text-[color:var(--gold)]">
          Reelibra
        </span>
        <span className="mono rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] px-1 py-0.5 text-[9px] font-medium text-[color:var(--gold)]">
          β
        </span>
      </Link>

      <nav
        aria-label="Хлебные крошки"
        className="hidden min-w-0 flex-1 items-center gap-2.5 overflow-x-auto text-sm sm:flex"
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
                  aria-current={last ? "page" : undefined}
                >
                  {c.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-3 sm:gap-4">
        <ModeSwitch />
        <HealthIndicator />
      </div>
    </header>
  );
}
