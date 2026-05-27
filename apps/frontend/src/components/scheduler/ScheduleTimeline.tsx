
import { useState } from "react";
import { SCHEDULER_TZ } from "@/lib/constants/scheduler";
import type { ScheduleDistributionMode } from "@/lib/api/scheduler";

interface Props {
  mode: ScheduleDistributionMode;
  onModeChange: (mode: ScheduleDistributionMode) => void;
  timeOfDay: string;
  onTimeChange: (next: string) => void;
  // per_date
  dates: string[];
  onDatesChange: (next: string[]) => void;
  // single_day
  singleDayDate: string;
  onSingleDayDateChange: (next: string) => void;
  singleDayIntervalMin: number;
  onSingleDayIntervalChange: (next: number) => void;
  // serial
  serialStartDate: string;
  onSerialStartDateChange: (next: string) => void;
  serialIntervalDays: number;
  onSerialIntervalDaysChange: (next: number) => void;
  // info
  reelsCount: number;
  accountsCount: number;
}

function formatDateLabel(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("ru-RU", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDaysIso(iso: string, days: number): string {
  try {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${mm}-${dd}`;
  } catch {
    return iso;
  }
}

function addMinutesToTime(time: string, minutes: number): string {
  const [hhStr, mmStr] = time.split(":");
  const hh = parseInt(hhStr ?? "0", 10) || 0;
  const mm = parseInt(mmStr ?? "0", 10) || 0;
  const total = hh * 60 + mm + minutes;
  const dayMod = ((total % 1440) + 1440) % 1440;
  const outHh = Math.floor(dayMod / 60);
  const outMm = dayMod % 60;
  return `${String(outHh).padStart(2, "0")}:${String(outMm).padStart(2, "0")}`;
}

const MODES: { value: ScheduleDistributionMode; label: string; hint: string }[] = [
  {
    value: "per_date",
    label: "По датам вручную",
    hint: "Список дат, публикации раскладываются round-robin.",
  },
  {
    value: "single_day",
    label: "В один день",
    hint: "Все публикации в один день с интервалом в минутах.",
  },
  {
    value: "serial",
    label: "Серия каждые N дней",
    hint: "Каждое видео на своей дате с шагом в днях; аккаунты одного видео — в один день.",
  },
];

export function ScheduleTimeline({
  mode,
  onModeChange,
  timeOfDay,
  onTimeChange,
  dates,
  onDatesChange,
  singleDayDate,
  onSingleDayDateChange,
  singleDayIntervalMin,
  onSingleDayIntervalChange,
  serialStartDate,
  onSerialStartDateChange,
  serialIntervalDays,
  onSerialIntervalDaysChange,
  reelsCount,
  accountsCount,
}: Props) {
  const [draft, setDraft] = useState<string>(todayIso());

  const addDate = () => {
    if (!draft) return;
    if (dates.includes(draft)) return;
    const next = [...dates, draft].sort();
    onDatesChange(next);
  };

  const removeDate = (iso: string) => {
    onDatesChange(dates.filter((d) => d !== iso));
  };

  const totalPosts = reelsCount * accountsCount;

  // summary per mode
  let summary: React.ReactNode = null;
  if (mode === "per_date") {
    const datesCount = dates.length;
    summary = (
      <>
        <div className="text-sm text-[color:var(--paper)]">
          {totalPosts} публикаций ({reelsCount} рилсов × {accountsCount}{" "}
          аккаунтов) разложатся по {datesCount}{" "}
          {datesCount === 1 ? "дате" : "датам"}
        </div>
        {datesCount > 0 && totalPosts > 0 ? (
          <div className="text-[11px] text-[color:var(--text-secondary)]">
            Примерно {(totalPosts / datesCount).toFixed(1)} публикаций в день
          </div>
        ) : null}
      </>
    );
  } else if (mode === "single_day") {
    const lastIdx = Math.max(0, totalPosts - 1);
    const lastTime = addMinutesToTime(
      timeOfDay,
      singleDayIntervalMin * lastIdx,
    );
    const overflowDays = Math.floor(
      (timeToMinutes(timeOfDay) + singleDayIntervalMin * lastIdx) / 1440,
    );
    summary = (
      <>
        <div className="text-sm text-[color:var(--paper)]">
          {totalPosts} публикаций в один день —{" "}
          {formatDateLabel(singleDayDate)}
        </div>
        <div className="text-[11px] text-[color:var(--text-secondary)]">
          С {timeOfDay} до {lastTime}
          {overflowDays > 0 ? ` (+${overflowDays} дн.)` : ""}, шаг{" "}
          {singleDayIntervalMin} мин
        </div>
      </>
    );
  } else {
    // serial
    const lastVideoDate = addDaysIso(
      serialStartDate,
      serialIntervalDays * Math.max(0, reelsCount - 1),
    );
    summary = (
      <>
        <div className="text-sm text-[color:var(--paper)]">
          Серия из {reelsCount} видео × {accountsCount} аккаунтов ={" "}
          {totalPosts} публикаций
        </div>
        <div className="text-[11px] text-[color:var(--text-secondary)]">
          С {formatDateLabel(serialStartDate)} по{" "}
          {formatDateLabel(lastVideoDate)}, шаг {serialIntervalDays}{" "}
          {serialIntervalDays === 1 ? "день" : "дн."}; аккаунты одного видео — в
          один день с jitter 2 мин.
        </div>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Mode tabs */}
      <div className="flex flex-col gap-3">
        <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          Режим распределения
        </span>
        <div
          className="grid grid-cols-1 gap-2 sm:grid-cols-2"
          role="radiogroup"
          aria-label="Режим распределения"
        >
          {MODES.map((m) => {
            const active = m.value === mode;
            return (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => onModeChange(m.value)}
                className={`flex flex-col gap-1 rounded-md border px-3 py-2.5 text-left transition-colors ${
                  active
                    ? "border-[color:var(--gold)] bg-[color:var(--ink-2)]"
                    : "border-[color:var(--line)] bg-transparent hover:border-[color:var(--gold)]"
                }`}
              >
                <span
                  className={`text-[13px] ${
                    active
                      ? "text-[color:var(--paper)]"
                      : "text-[color:var(--paper-dim)]"
                  }`}
                >
                  {m.label}
                </span>
                <span className="text-[11px] text-[color:var(--text-secondary)]">
                  {m.hint}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Common: time + tz */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            {mode === "per_date"
              ? "Время публикации"
              : mode === "single_day"
                ? "Время первого слота"
                : "Время публикации"}
          </span>
          <input
            type="time"
            value={timeOfDay}
            onChange={(e) => onTimeChange(e.target.value)}
            className="w-36 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
          />
          <span className="text-[11px] text-[color:var(--text-secondary)]">
            {mode === "single_day"
              ? "С него начнётся цепочка слотов"
              : "Единое время для всех аккаунтов"}
          </span>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            Часовой пояс
          </span>
          <input
            type="text"
            value={`${SCHEDULER_TZ} (+07)`}
            readOnly
            className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink)] px-3 py-2 text-[13px] text-[color:var(--paper-dim)] outline-none"
          />
          <span className="text-[11px] text-[color:var(--text-secondary)]">
            Зафиксирован для всего проекта
          </span>
        </label>
      </div>

      {/* Mode-specific controls */}
      {mode === "per_date" ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Добавить дату
              </span>
              <input
                type="date"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
              />
            </label>
            <button
              type="button"
              onClick={addDate}
              disabled={!draft || dates.includes(draft)}
              className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              + Добавить
            </button>
          </div>

          {dates.length === 0 ? (
            <div className="surface-card flex items-center justify-center p-6 text-center text-sm text-[color:var(--text-secondary)]">
              Добавь хотя бы одну дату — кампания разложится равномерно
            </div>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {dates.map((iso) => (
                <li
                  key={iso}
                  className="mono flex items-center gap-2 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-1.5 text-[12px] text-[color:var(--paper)]"
                >
                  <span>{formatDateLabel(iso)}</span>
                  <button
                    type="button"
                    onClick={() => removeDate(iso)}
                    aria-label={`Удалить ${iso}`}
                    className="text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--danger)]"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {mode === "single_day" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Дата публикации
            </span>
            <input
              type="date"
              value={singleDayDate}
              onChange={(e) => onSingleDayDateChange(e.target.value)}
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
            <span className="text-[11px] text-[color:var(--text-secondary)]">
              Все публикации пойдут в этот день
            </span>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Интервал между слотами, минут
            </span>
            <input
              type="number"
              min={1}
              max={1440}
              value={singleDayIntervalMin}
              onChange={(e) =>
                onSingleDayIntervalChange(
                  Math.max(1, Math.min(1440, Number(e.target.value) || 1)),
                )
              }
              className="w-36 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
            <span className="text-[11px] text-[color:var(--text-secondary)]">
              Шаг между соседними публикациями (1–1440)
            </span>
          </label>
        </div>
      ) : null}

      {mode === "serial" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Базовая дата (первое видео)
            </span>
            <input
              type="date"
              value={serialStartDate}
              onChange={(e) => onSerialStartDateChange(e.target.value)}
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
            <span className="text-[11px] text-[color:var(--text-secondary)]">
              С этой даты стартует серия
            </span>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Шаг между видео, дней
            </span>
            <input
              type="number"
              min={1}
              max={365}
              value={serialIntervalDays}
              onChange={(e) =>
                onSerialIntervalDaysChange(
                  Math.max(1, Math.min(365, Number(e.target.value) || 1)),
                )
              }
              className="w-36 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
            <span className="text-[11px] text-[color:var(--text-secondary)]">
              Каждое следующее видео публикуется через N дней (1–365)
            </span>
          </label>
        </div>
      ) : null}

      {/* Summary */}
      <div className="surface-card flex flex-col gap-1.5 p-4">
        <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          предварительный расчёт
        </div>
        {summary}
      </div>
    </div>
  );
}

function timeToMinutes(time: string): number {
  const [hhStr, mmStr] = time.split(":");
  const hh = parseInt(hhStr ?? "0", 10) || 0;
  const mm = parseInt(mmStr ?? "0", 10) || 0;
  return hh * 60 + mm;
}
