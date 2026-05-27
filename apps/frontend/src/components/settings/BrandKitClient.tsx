
import { useState, type ChangeEvent } from "react";

interface BrandKit {
  primary_color: string;
  secondary_color: string;
  text_color: string;
  logo_data_url: string | null;
  font_family: string;
}

const DEFAULT_KIT: BrandKit = {
  primary_color: "#b79b5b",
  secondary_color: "#2f2b26",
  text_color: "#f5f1ea",
  logo_data_url: null,
  font_family: "Inter",
};

const LS_KEY = "videomaker.brand_kit";
const MAX_LOGO_BYTES = 1_500_000;

const COLOR_FIELDS: Array<{
  key: "primary_color" | "secondary_color" | "text_color";
  label: string;
  hint: string;
}> = [
  {
    key: "primary_color",
    label: "Основной",
    hint: "Акцент, активные кнопки",
  },
  {
    key: "secondary_color",
    label: "Поддерживающий",
    hint: "Карточки, фон на сабах",
  },
  {
    key: "text_color",
    label: "Текст",
    hint: "Цвет субтитров и заголовков",
  },
];

function loadKitFromStorage(): BrandKit {
  if (typeof window === "undefined") return DEFAULT_KIT;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return DEFAULT_KIT;
    const parsed = JSON.parse(raw) as Partial<BrandKit>;
    return { ...DEFAULT_KIT, ...parsed };
  } catch {
    return DEFAULT_KIT;
  }
}

export function BrandKitClient() {
  const [kit, setKit] = useState<BrandKit>(loadKitFromStorage);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onLogoChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setError("Лого больше 1.5 МБ — сожми перед загрузкой.");
      return;
    }
    setError(null);
    const reader = new FileReader();
    reader.onload = () =>
      setKit((prev) => ({ ...prev, logo_data_url: String(reader.result) }));
    reader.onerror = () => setError("Не удалось прочитать файл.");
    reader.readAsDataURL(file);
  };

  const onRemoveLogo = () =>
    setKit((prev) => ({ ...prev, logo_data_url: null }));

  const onReset = () => {
    setKit(DEFAULT_KIT);
    setError(null);
  };

  const onSave = () => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(LS_KEY, JSON.stringify(kit));
      setSavedFlash(true);
      setError(null);
      setTimeout(() => setSavedFlash(false), 1500);
    } catch {
      setError(
        "Не получилось сохранить — в браузере кончилось место. Очисти кэш и попробуй снова.",
      );
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <section className="surface-card flex flex-col gap-4 p-5">
        <div className="divider">цвета</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {COLOR_FIELDS.map(({ key, label, hint }) => (
            <label key={key} className="flex flex-col gap-2">
              <div className="flex flex-col gap-0.5">
                <span className="text-[12px] font-medium text-[color:var(--paper)]">
                  {label}
                </span>
                <span className="text-[11px] text-[color:var(--mute-2)]">
                  {hint}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={kit[key]}
                  onChange={(e) =>
                    setKit((prev) => ({ ...prev, [key]: e.target.value }))
                  }
                  className="h-10 w-14 cursor-pointer rounded-none border border-[color:var(--line)] bg-transparent p-0.5"
                />
                <input
                  type="text"
                  value={kit[key]}
                  onChange={(e) =>
                    setKit((prev) => ({ ...prev, [key]: e.target.value }))
                  }
                  spellCheck={false}
                  className="flex-1 rounded-none border border-[color:var(--line)] bg-[color:var(--ink-2)] px-2 py-1.5 font-mono text-[11px] uppercase text-[color:var(--paper)] focus:border-[color:var(--gold)] focus:outline-none"
                />
              </div>
            </label>
          ))}
        </div>
      </section>

      <section className="surface-card flex flex-col gap-4 p-5">
        <div className="divider">шрифт</div>
        <label className="flex flex-col gap-1">
          <span className="text-[12px] font-medium text-[color:var(--paper)]">
            Имя семьи
          </span>
          <input
            type="text"
            value={kit.font_family}
            onChange={(e) =>
              setKit((prev) => ({ ...prev, font_family: e.target.value }))
            }
            placeholder="Inter, Montserrat, PT Sans..."
            className="rounded-none border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] focus:border-[color:var(--gold)] focus:outline-none"
          />
          <span className="text-[11px] text-[color:var(--mute-2)]">
            Имя должно совпадать с пресетом шрифтов в настройках субтитров.
          </span>
        </label>
      </section>

      <section className="surface-card flex flex-col gap-4 p-5">
        <div className="divider">логотип</div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="flex-1">
            <label className="flex cursor-pointer flex-col items-start gap-2 rounded-none border border-dashed border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-3 text-[12px] text-[color:var(--mute-2)] transition-colors hover:border-[color:var(--mute)]">
              <span>Выбрать PNG или JPG (до 1.5 МБ)</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                onChange={onLogoChange}
                className="text-[11px] text-[color:var(--paper-dim)]"
              />
            </label>
            {error && (
              <p className="mt-2 text-[11px] text-[color:var(--danger)]">
                {error}
              </p>
            )}
          </div>
          {kit.logo_data_url && (
            <div className="flex flex-col items-start gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={kit.logo_data_url}
                alt="Логотип"
                className="h-20 w-auto rounded-none border border-[color:var(--line)] bg-white p-1"
              />
              <button
                type="button"
                onClick={onRemoveLogo}
                className="text-[11px] uppercase tracking-[0.1em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--danger)]"
              >
                Убрать
              </button>
            </div>
          )}
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          className="btn btn-primary"
        >
          {savedFlash ? "Сохранено" : "Сохранить"}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="rounded-none border border-[color:var(--line)] px-4 py-2 text-[13px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
        >
          Сбросить
        </button>
        <span className="text-[11px] text-[color:var(--mute-2)]">
          Данные хранятся локально. Интеграция с субтитрами и пост-продакшн
          пресетами — следующий шаг.
        </span>
      </div>
    </div>
  );
}
