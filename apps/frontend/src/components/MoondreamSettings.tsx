
import { useState, useTransition } from "react";
import {
  api,
  type VisionSettingsResponse,
  type VisionBackend,
} from "@/lib/api";
import { humanizeError } from "@/lib/humanizeError";

interface Props {
  initial: VisionSettingsResponse;
}

const BACKEND_LABEL: Record<VisionBackend, string> = {
  metal: "GPU (Metal)",
  cpu: "CPU",
  unavailable: "не запущен",
};

const SAMPLE_RATE_MIN = 0.5;
const SAMPLE_RATE_MAX = 60.0;
const SAMPLE_RATE_STEP = 0.5;

export function MoondreamSettings({ initial }: Props) {
  const [data, setData] = useState<VisionSettingsResponse>(initial);
  const [pendingEnabled, setPendingEnabled] = useState(initial.settings.enabled);
  const [pendingRate, setPendingRate] = useState(
    initial.settings.frame_sample_rate_sec,
  );
  const [status, setStatus] = useState<
    | { kind: "idle" }
    | { kind: "saving" }
    | { kind: "error"; message: string }
    | { kind: "saved" }
  >({ kind: "idle" });
  const [isPending, startTransition] = useTransition();

  const dirty =
    pendingEnabled !== data.settings.enabled ||
    pendingRate !== data.settings.frame_sample_rate_sec;

  async function save() {
    setStatus({ kind: "saving" });
    try {
      const updated = await api.updateVisionSettings({
        enabled: pendingEnabled,
        frame_sample_rate_sec: pendingRate,
      });
      const fresh = await api.getVisionSettings();
      setData(fresh);
      setPendingEnabled(updated.enabled);
      setPendingRate(updated.frame_sample_rate_sec);
      setStatus({ kind: "saved" });
      setTimeout(() => setStatus({ kind: "idle" }), 2500);
    } catch (err) {
      const human = humanizeError(err);
      setStatus({
        kind: "error",
        message: `${human.title}. ${human.detail}`,
      });
    }
  }

  const healthColor = data.health.available
    ? data.settings.enabled
      ? "bg-[color:var(--success)]"
      : "bg-[color:var(--warning)]"
    : "bg-[color:var(--border-default)]";

  return (
    <section className="surface-card p-5 md:col-span-2">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
            Визуальный анализ (Moondream 2)
          </h2>
          <p className="text-xs text-[color:var(--text-secondary)]">
            Анализ кадров локально на этом компьютере. Интернет не нужен. При
            первом запуске загружает модель весом ~4,5 ГБ — это около пары
            минут на хорошем канале.
          </p>
        </div>
        <span
          className={`mt-1 size-2 shrink-0 rounded-full ${healthColor}`}
          aria-hidden="true"
        />
      </header>

      <div className="grid grid-cols-1 gap-x-4 text-sm sm:grid-cols-2">
        <StatusRow label="Включён">
          <span
            className={
              data.settings.enabled
                ? "text-[color:var(--success)] font-medium"
                : "text-[color:var(--text-muted)]"
            }
          >
            {data.settings.enabled ? "да" : "нет"}
          </span>
        </StatusRow>
        <StatusRow label="Ускоритель">
          <span className="font-mono text-xs text-[color:var(--text-secondary)]">
            {BACKEND_LABEL[data.health.backend]}
          </span>
        </StatusRow>
        <StatusRow label="Библиотека">
          <span
            className={
              data.health.available
                ? "text-[color:var(--success)]"
                : "text-[color:var(--danger)]"
            }
          >
            {data.health.available ? "готова" : "не найдена"}
          </span>
        </StatusRow>
        <StatusRow label="Модель">
          <span
            className={
              data.health.model_loaded
                ? "text-[color:var(--success)]"
                : "text-[color:var(--text-muted)]"
            }
          >
            {data.health.model_loaded
              ? "в памяти"
              : "загрузится при первом использовании"}
          </span>
        </StatusRow>
        <StatusRow label="Источник модели">
          <span className="font-mono text-xs text-[color:var(--text-muted)]">
            {data.gguf_repo}
          </span>
        </StatusRow>
        <StatusRow label="Частота анализа">
          <span className="font-mono text-xs text-[color:var(--text-muted)]">
            1 кадр каждые {data.settings.frame_sample_rate_sec.toFixed(1)} с
          </span>
        </StatusRow>
      </div>

      {data.health.error && !data.settings.enabled ? (
        <p className="mt-4 text-xs text-[color:var(--text-muted)]">
          {data.health.error}
        </p>
      ) : null}
      {data.health.error && data.settings.enabled ? (
        <p className="mt-4 rounded-lg border border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 p-3 text-xs text-[color:var(--danger)]">
          {data.health.error}
        </p>
      ) : null}

      <hr className="my-5 border-[color:var(--border-subtle)]" />

      <div className="flex flex-col gap-5">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={pendingEnabled}
            onChange={(e) => setPendingEnabled(e.target.checked)}
            className="mt-0.5 size-4 rounded border-[color:var(--border-default)] accent-[color:var(--accent-primary)]"
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-sm text-[color:var(--text-primary)]">
              Включить анализ кадров · экспериментально, opt-in
            </span>
            <span className="text-xs text-[color:var(--text-muted)]">
              Умный монтаж замечает композицию лиц, выбирает обложку рилса
              и учитывает визуальные эффекты при нарезке. По умолчанию выключено:
              заметно удлиняет обработку, включай осознанно.
            </span>
          </span>
        </label>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label
              htmlFor="vision-sample-rate"
              className="text-sm text-[color:var(--text-primary)]"
            >
              Как часто смотреть в видео
            </label>
            <span className="font-mono text-xs text-[color:var(--text-muted)]">
              каждые {pendingRate.toFixed(1)} с
            </span>
          </div>
          <input
            id="vision-sample-rate"
            type="range"
            min={SAMPLE_RATE_MIN}
            max={SAMPLE_RATE_MAX}
            step={SAMPLE_RATE_STEP}
            value={pendingRate}
            onChange={(e) => setPendingRate(parseFloat(e.target.value))}
            disabled={!pendingEnabled}
            className="w-full accent-[color:var(--accent-primary)] disabled:opacity-40"
          />
          <p className="text-xs text-[color:var(--text-muted)]">
            Меньше — точнее анализ, но дольше обработка. По умолчанию 10
            секунд — это около 180 кадров на получасовом видео.
          </p>
        </div>

        <div className="flex items-center justify-between gap-4 pt-1">
          <div className="text-xs">
            {status.kind === "error" ? (
              <span className="text-[color:var(--danger)]">
                Не получилось сохранить: {status.message}
              </span>
            ) : status.kind === "saved" ? (
              <span className="font-medium text-[color:var(--success)]">
                Настройки сохранены.
              </span>
            ) : status.kind === "saving" ? (
              <span className="text-[color:var(--text-secondary)]">
                Сохраняем…
              </span>
            ) : dirty ? (
              <span className="text-[color:var(--warning)]">
                Есть несохранённые изменения
              </span>
            ) : (
              <span className="text-[color:var(--text-muted)]">—</span>
            )}
          </div>
          <button
            type="button"
            onClick={() => startTransition(save)}
            disabled={!dirty || isPending || status.kind === "saving"}
            className="rounded-lg bg-[color:var(--accent-primary)] px-4 py-2 text-sm font-semibold text-[color:var(--accent-on-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)] disabled:shadow-none"
          >
            Сохранить
          </button>
        </div>
      </div>
    </section>
  );
}

function StatusRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-[color:var(--border-subtle)] py-2 last:border-b-0">
      <span className="text-[11px] uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        {label}
      </span>
      {children}
    </div>
  );
}
