
import { Link } from "react-router-dom";
import { usePathname } from "@/lib/router-compat";

interface Item {
  href: string;
  code: string;
  label: string;
  hint: string;
}

const ITEMS: Item[] = [
  {
    href: "/settings/profiles",
    code: "PRF",
    label: "Профили нарезки",
    hint: "Говорящая голова, фэшн, путешествия, скринкаст, своё",
  },
  {
    href: "/settings/models",
    code: "MDL",
    label: "Модели",
    hint: "LLM-провайдеры, распознавание речи, визуальный анализ",
  },
  {
    href: "/settings/performance",
    code: "PRF",
    label: "Производительность",
    hint: "Рабочая копия, параллелизм, размер чанков",
  },
  {
    href: "/settings/subtitles",
    code: "CAP",
    label: "Субтитры",
    hint: "Пресеты шрифтов, положения, эффектов",
  },
  {
    href: "/settings/post-production",
    code: "POP",
    label: "Пост-продакшн",
    hint: "Интро и аутро, нормализация звука, зум",
  },
  {
    href: "/settings/brand",
    code: "BRN",
    label: "Фирменные стили",
    hint: "Цвета, шрифт и логотип для субтитров и пресетов",
  },
  {
    href: "/settings/prompts",
    code: "PMT",
    label: "Промпты",
    hint: "Системные инструкции для этапов анализа",
  },
  {
    href: "/settings/maintenance",
    code: "MNT",
    label: "Обслуживание",
    hint: "Кэш proxy-файлов и шрифтов · эксперт-режим",
  },
];

export function SettingsSubNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Разделы настроек" className="flex flex-col gap-1">
      <div className="divider mb-4">настройки</div>
      {ITEMS.map((item) => {
        const active =
          item.href === "/settings/profiles"
            ? pathname === "/settings/profiles"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            to={item.href}
            aria-current={active ? "page" : undefined}
            className={[
              "group flex items-start gap-3 rounded-none px-[10px] py-[10px] transition-colors duration-150",
              active
                ? "bg-[color:var(--ink-2)] text-[color:var(--paper)]"
                : "text-[color:var(--mute-2)] hover:bg-[color:var(--ink-2)] hover:text-[color:var(--paper)]",
            ].join(" ")}
            style={{
              borderLeft: active
                ? "2px solid var(--paper)"
                : "2px solid transparent",
            }}
          >
            <span
              className="mono shrink-0"
              style={{
                fontSize: 10,
                width: 26,
                letterSpacing: "0.1em",
                opacity: active ? 1 : 0.7,
                marginTop: 2,
              }}
            >
              {item.code}
            </span>
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="text-[13px]">{item.label}</span>
              <span
                className={`text-[11px] leading-snug ${
                  active
                    ? "text-[color:var(--paper-dim)]"
                    : "text-[color:var(--mute)]"
                }`}
              >
                {item.hint}
              </span>
            </div>
          </Link>
        );
      })}
    </nav>
  );
}
