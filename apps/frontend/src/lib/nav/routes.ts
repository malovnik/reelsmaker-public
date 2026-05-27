/**
 * Единый словарь навигации Reelibra — один источник правды (U-02).
 *
 * Потребители: NavRail (4 зоны), SettingsSubNav (8 разделов), хлебные крошки,
 * онбординг. Раньше NavRail и SettingsSubNav держали свои списки с разными
 * `code`/`label` для одного раздела → рассинхрон. Здесь — одна структура.
 *
 * Модель (d4 §1.2): «3 рабочие зоны + Настройки».
 *   - Рейл рендерит только NAV_ZONES (4 пункта).
 *   - Внутри /settings/* SettingsSubNav рендерит SETTINGS_SECTIONS (8 пунктов),
 *     включая ранее недостижимые brand/maintenance.
 */

/** Верхнеуровневая рабочая зона продукта (пункт рейла). */
export interface NavZone {
  /** Mono-код раздела (брендбук): «STU», «LIB»… */
  code: string;
  /** Человеческий ярлык. */
  label: string;
  /** Целевой href. */
  href: string;
  /**
   * Префикс пути для подсветки активности. Зона активна, когда
   * `pathname` принадлежит любому из `matchPrefixes`.
   * Для Студии префикс не используется — только точное совпадение `/`.
   */
  matchPrefixes: string[];
  /** Студия активна только на точном `/` (а не на любом пути). */
  exact?: boolean;
}

/** Раздел настроек (пункт SettingsSubNav). */
export interface SettingsSection {
  code: string;
  label: string;
  href: string;
}

/**
 * Четыре зоны рейла. Порядок = порядок отображения.
 * Студия активна только на «/»; остальные — по префиксам.
 */
export const NAV_ZONES: NavZone[] = [
  { code: "STU", label: "Студия", href: "/", matchPrefixes: ["/"], exact: true },
  {
    code: "LIB",
    label: "Проекты",
    href: "/projects",
    matchPrefixes: ["/projects", "/jobs"],
  },
  {
    code: "PLN",
    label: "Планировщик",
    href: "/scheduler",
    matchPrefixes: ["/scheduler"],
  },
  {
    code: "CFG",
    label: "Настройки",
    href: "/settings/profiles",
    matchPrefixes: ["/settings"],
  },
];

/**
 * Восемь разделов настроек. Порядок = порядок в SettingsSubNav.
 * Первый раздел (Профили) — точка входа зоны CFG.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  { code: "PRF", label: "Профили нарезки", href: "/settings/profiles" },
  { code: "MDL", label: "Модели", href: "/settings/models" },
  { code: "KEY", label: "Ключи API", href: "/settings/api-keys" },
  { code: "PFM", label: "Производительность", href: "/settings/performance" },
  { code: "CAP", label: "Субтитры", href: "/settings/subtitles" },
  { code: "POP", label: "Пост-продакшн", href: "/settings/post-production" },
  { code: "BRN", label: "Фирменные стили", href: "/settings/brand" },
  { code: "PMT", label: "Промпты", href: "/settings/prompts" },
  { code: "MNT", label: "Обслуживание", href: "/settings/maintenance" },
];

/** Точка входа зоны «Настройки» (первый раздел). */
export const SETTINGS_ENTRY = SETTINGS_SECTIONS[0].href;

/**
 * Проверка активности зоны рейла для текущего `pathname`.
 * Студия (`exact`) активна лишь на точном «/».
 */
export function isZoneActive(zone: NavZone, pathname: string): boolean {
  if (zone.exact) return pathname === zone.href;
  return zone.matchPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Проверка активности раздела настроек. Профили активны только на точном
 * `/settings/profiles` (иначе родитель перехватит вложенные пути).
 */
export function isSectionActive(section: SettingsSection, pathname: string): boolean {
  if (section.href === SETTINGS_ENTRY) return pathname === SETTINGS_ENTRY;
  return pathname === section.href || pathname.startsWith(`${section.href}/`);
}
