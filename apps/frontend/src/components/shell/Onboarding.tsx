import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui";
import { useUiMode } from "@/contexts";
import type { UiMode } from "@/contexts";
import { coreApi, type HealthResponse } from "@/lib/api/core";

/**
 * Welcome-экран первого запуска (d4 §3). Показывается, когда нет флага
 * reelibra.onboarded ИЛИ система не готова (нет GEMINI_API_KEY / ffmpeg).
 * Три блока: готовность (health-gate) → выбор режима → первое действие.
 * Не навязчивый: «Осмотреться сам» закрывает оверлей и пишет флаг.
 */

const ONBOARDED_KEY = "reelibra.onboarded";

interface CheckItem {
  key: string;
  label: string;
  ok: boolean;
  /** Инлайн-инструкция, когда пункт красный. */
  fix?: string;
}

function readOnboarded(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(ONBOARDED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeOnboarded() {
  try {
    window.localStorage.setItem(ONBOARDED_KEY, "1");
  } catch {
    // localStorage недоступен — оверлей просто не покажется заново в этой сессии.
  }
}

function buildChecks(health: HealthResponse): CheckItem[] {
  return [
    {
      key: "gemini",
      label: "Ключ Gemini",
      ok: health.llm_providers.length > 0,
      fix: "Добавьте GEMINI_API_KEY в переменные окружения и перезапустите — без него нарезка не запустится.",
    },
    {
      key: "ffmpeg",
      label: "FFmpeg",
      // Бэкенд не отдаёт ffmpeg в /health напрямую; наличие транскрайберов и
      // успешный ответ — косвенный признак готовности медиа-стека.
      ok: health.transcribers.length > 0 || health.llm_providers.length > 0,
      fix: "Установите FFmpeg на сервере и перезапустите бэкенд.",
    },
    {
      key: "stt",
      label: "Распознавание речи",
      ok: health.transcribers.length > 0,
      fix: "Не найден ни один движок распознавания речи. Проверьте настройки субтитров.",
    },
  ];
}

const MODE_CARDS: { mode: UiMode; title: string; desc: string }[] = [
  {
    mode: "guided",
    title: "Пошаговый",
    desc: "Проведу за руку: источник → стиль → запуск. Опытные детали спрятаны.",
  },
  {
    mode: "expert",
    title: "Эксперт",
    desc: "Все параметры на одном экране. Для тех, кто уже резал.",
  },
];

export function Onboarding() {
  const navigate = useNavigate();
  const { mode, setMode } = useUiMode();
  const [open, setOpen] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(true);

  const loadHealth = useCallback(async () => {
    setChecking(true);
    try {
      const data = await coreApi.health();
      setHealth(data);
      return data;
    } catch {
      setHealth(null);
      return null;
    } finally {
      setChecking(false);
    }
  }, []);

  // Решение о показе: при монтировании читаем флаг + пингуем health.
  useEffect(() => {
    let alive = true;
    void (async () => {
      const data = await loadHealth();
      if (!alive) return;
      const onboarded = readOnboarded();
      const notReady = !data || data.llm_providers.length === 0;
      setOpen(!onboarded || notReady);
    })();
    return () => {
      alive = false;
    };
  }, [loadHealth]);

  if (!open) return null;

  const checks = health ? buildChecks(health) : [];
  const hasBlocker = !health || checks.some((c) => !c.ok);

  const close = () => {
    writeOnboarded();
    setOpen(false);
  };

  const start = () => {
    if (hasBlocker) return;
    writeOnboarded();
    setOpen(false);
    navigate("/");
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
      className="fixed inset-0 z-[200] flex items-center justify-center overflow-y-auto bg-[color:var(--ink)] px-4 py-8"
    >
      {/* Фоновый энсо ~8% — как в hero брендбука. */}
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 -z-0 size-[520px] -translate-x-1/2 -translate-y-1/2 opacity-[0.06]"
        viewBox="0 0 100 100"
      >
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke="var(--gold)"
          strokeWidth="3"
          strokeDasharray="230 40"
          strokeLinecap="round"
        />
      </svg>

      <div className="relative z-10 w-full max-w-xl rounded-none border border-[color:var(--line)] bg-[color:var(--ink-2)] p-6 md:p-8">
        <div className="flex items-center gap-2.5">
          <span className="display-serif text-[1.5rem] font-semibold leading-none tracking-[-0.025em] text-[color:var(--gold)]">
            Reelibra
          </span>
          <span className="mono rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--gold)]">
            β
          </span>
        </div>
        <h1
          id="onboarding-title"
          className="mt-4 font-[family-name:var(--font-display)] text-2xl font-semibold leading-tight text-[color:var(--paper)]"
        >
          Нарезаю длинные видео на вертикальные клипы
        </h1>
        <p className="mt-2 text-[0.9375rem] leading-relaxed text-[color:var(--mute-2)]">
          Загрузите интервью, подкаст или эфир — соберу из него готовые
          вертикальные клипы. Перед стартом проверим, всё ли на месте.
        </p>

        {/* Блок A — готовность системы */}
        <section className="mt-6">
          <div className="mono mb-3 text-[10px] uppercase tracking-[0.14em] text-[color:var(--copper,var(--ember))]">
            Готовность
          </div>
          {checking && !health ? (
            <p className="text-[0.875rem] text-[color:var(--mute-2)]">Проверяю сервер…</p>
          ) : !health ? (
            <p className="text-[0.875rem] leading-relaxed text-[color:var(--danger)]">
              Нет связи с сервером. Проверьте, запущен ли бэкенд, и нажмите
              «Проверить снова».
            </p>
          ) : (
            <ul className="space-y-2.5">
              {checks.map((c) => (
                <li key={c.key} className="flex gap-2.5 text-[0.875rem] leading-snug">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 shrink-0 font-medium"
                    style={{ color: c.ok ? "var(--gold)" : "var(--danger)" }}
                  >
                    {c.ok ? "✓" : "✗"}
                  </span>
                  <span>
                    <span className="text-[color:var(--paper)]">{c.label}</span>
                    {!c.ok && c.fix ? (
                      <span className="mt-1 block text-[color:var(--mute-2)]">{c.fix}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3">
            <Button
              variant="secondary"
              size="sm"
              loading={checking}
              onClick={() => void loadHealth()}
            >
              Проверить снова
            </Button>
          </div>
        </section>

        {/* Блок B — выбор режима */}
        <section className="mt-6">
          <div className="mono mb-3 text-[10px] uppercase tracking-[0.14em] text-[color:var(--copper,var(--ember))]">
            Как работать
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {MODE_CARDS.map((card) => {
              const active = card.mode === mode;
              return (
                <button
                  key={card.mode}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setMode(card.mode)}
                  className={[
                    "rounded-none border p-4 text-left transition-colors duration-150",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--gold)]",
                    active
                      ? "border-[color:var(--gold)] bg-[color:var(--ink-3)]"
                      : "border-[color:var(--line)] bg-transparent hover:border-[color:var(--mute)]",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      aria-hidden="true"
                      className="h-3.5 w-1 shrink-0 bg-[color:var(--gold)]"
                    />
                    <span className="font-[family-name:var(--font-display)] text-base font-semibold text-[color:var(--paper)]">
                      {card.title}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[0.8125rem] leading-snug text-[color:var(--mute-2)]">
                    {card.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </section>

        {/* Блок C — первое действие */}
        <section className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button
            variant="primary"
            size="lg"
            disabled={hasBlocker}
            onClick={start}
            title={
              hasBlocker
                ? "Сначала закройте красные пункты в готовности"
                : undefined
            }
          >
            Создать первую нарезку
          </Button>
          <button
            type="button"
            onClick={close}
            className="text-[0.875rem] text-[color:var(--mute-2)] underline-offset-4 transition-colors hover:text-[color:var(--paper)] hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--gold)]"
          >
            Осмотреться сам
          </button>
        </section>

        {hasBlocker && health ? (
          <p className="mt-3 text-[0.8125rem] leading-snug text-[color:var(--mute-2)]">
            Кнопка «Создать» включится, когда все пункты готовности станут
            зелёными.
          </p>
        ) : null}
      </div>
    </div>
  );
}
