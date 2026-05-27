import { Link } from "react-router-dom";
import { usePathname } from "@/lib/router-compat";

interface NavItem {
  href: string;
  code: string;
  label: string;
  matchPrefix?: string;
  disabled?: boolean;
}

const ITEMS: NavItem[] = [
  { href: "/", code: "DSH", label: "Студия", matchPrefix: "/" },
  { href: "/projects", code: "PRJ", label: "Проекты", matchPrefix: "/projects" },
  { href: "/scheduler", code: "SCH", label: "Шедулер", matchPrefix: "/scheduler" },
  { href: "/settings/profiles", code: "PRF", label: "Профили", matchPrefix: "/settings" },
  { href: "/settings/models", code: "MDL", label: "Модели", matchPrefix: "/settings/models" },
  { href: "/settings/subtitles", code: "CAP", label: "Субтитры", matchPrefix: "/settings/subtitles" },
  { href: "/settings/post-production", code: "POP", label: "Пост-продакшн", matchPrefix: "/settings/post-production" },
  { href: "/settings/prompts", code: "PMT", label: "Промпты", matchPrefix: "/settings/prompts" },
  { href: "/settings/performance", code: "PFM", label: "Производительность", matchPrefix: "/settings/performance" },
];

function isActive(pathname: string, item: NavItem): boolean {
  const prefix = item.matchPrefix ?? item.href;
  if (prefix === "/") return pathname === "/";
  if (item.href === "/settings/profiles") return pathname === "/settings/profiles";
  return pathname.startsWith(prefix);
}

interface Props {
  /**
   * На viewport <1024px рейл скрыт. `mobileOpen` управляет drawer-режимом:
   * фиксированная панель поверх контента + затемнение фона.
   */
  mobileOpen?: boolean;
  onClose?: () => void;
}

export function NavRail({ mobileOpen = false, onClose }: Props) {
  const pathname = usePathname();

  return (
    <>
      {/* Затемнение позади drawer на mobile. На desktop никогда не виден. */}
      <button
        type="button"
        aria-label="Закрыть навигацию"
        onClick={onClose}
        className={[
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-200 lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
      />
      <aside
        className={[
          // Mobile: drawer поверх контента, скрыт по умолчанию
          "fixed inset-y-0 left-0 z-50 flex h-screen w-[280px] shrink-0 flex-col border-r border-[color:var(--line-soft)] bg-[color:var(--ink-2)] transition-transform duration-200 ease-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // Desktop: sticky-рейл в потоке, всегда виден. Чуть шире (232px)
          // чтобы пункты с bigger font не подрезались.
          "lg:sticky lg:top-0 lg:z-auto lg:w-[232px] lg:translate-x-0",
        ].join(" ")}
        aria-label="Главная навигация"
      >
        <div className="flex items-center justify-between border-b border-[color:var(--line-soft)] px-5 py-6">
          <div className="flex flex-col">
            <div className="flex items-center gap-2.5">
              <Link
                to="/"
                className="display-serif text-[1.5rem] font-semibold leading-none tracking-[-0.025em] text-[color:var(--paper)]"
                aria-label="Reelibra — на главную"
              >
                Reelibra
              </Link>
              <span className="mono rounded-md border border-[color:var(--line)] bg-[color:var(--ink-3)] px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--gold)]">
                β
              </span>
            </div>
            <div className="mono micro mute mt-3">студия · v.3.0</div>
          </div>
          {/* Закрывающий крестик — только на mobile когда drawer открыт */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть навигацию"
            className="-mr-1 inline-flex size-8 items-center justify-center rounded-md text-[color:var(--mute-2)] transition-colors hover:bg-[color:var(--ink-2)] hover:text-[color:var(--paper)] lg:hidden"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 overflow-auto px-3 py-4">
          {ITEMS.map((item) => {
            const active = isActive(pathname, item);
            return (
              <Link
                key={`${item.code}-${item.href}`}
                to={item.disabled ? "#" : item.href}
                aria-current={active ? "page" : undefined}
                aria-disabled={item.disabled || undefined}
                className={[
                  "group relative mb-0.5 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150",
                  active
                    ? "bg-[color:var(--ink-3)] text-[color:var(--paper)]"
                    : "text-[color:var(--mute-2)] hover:bg-[color:var(--ink-3)] hover:text-[color:var(--paper)]",
                  item.disabled ? "pointer-events-none opacity-40" : "",
                ].join(" ")}
              >
                {/* Активный индикатор — gold dot слева, не борд */}
                <span
                  aria-hidden="true"
                  className={[
                    "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full transition-all",
                    active
                      ? "bg-[color:var(--gold)] opacity-100"
                      : "bg-transparent opacity-0",
                  ].join(" ")}
                />
                <span
                  className="mono shrink-0 text-[10px] tracking-[0.14em]"
                  style={{
                    width: 28,
                    opacity: active ? 0.9 : 0.55,
                    color: active ? "var(--gold)" : "inherit",
                  }}
                >
                  {item.code}
                </span>
                <span className="text-[0.9375rem] font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-[color:var(--line-soft)] px-5 py-4">
          <div className="divider mb-3">язык</div>
          <div className="text-sm text-[color:var(--paper)]">Русский</div>
          <div className="mono mute mt-1 text-[10px] tracking-[0.14em]">
            target · ru · 1080p
          </div>
        </div>
      </aside>
    </>
  );
}
