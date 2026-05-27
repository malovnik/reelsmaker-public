
import { useRouter } from "@/lib/router-compat";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  schedulerApi,
  type AccountProfile,
  type LikedReelRef,
  type PublerAccount,
  type ScheduleDistributionMode,
} from "@/lib/api/scheduler";
import type { Project } from "@/lib/api/projects";
import { SCHEDULER_TZ } from "@/lib/constants/scheduler";
import { ReelPicker } from "./ReelPicker";
import { AccountsPicker } from "./AccountsPicker";
import { ScheduleTimeline } from "./ScheduleTimeline";

interface Props {
  accounts: PublerAccount[];
  profiles: AccountProfile[];
  likedReels: LikedReelRef[];
  projects: Project[];
}

type Step = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<Step, string> = {
  1: "Источник",
  2: "Назначения",
  3: "Расписание",
  4: "Подтверждение",
};

function defaultCampaignName(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `Кампания ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(
    now.getDate(),
  )} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function formatDateLabel(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

const MODE_LABEL: Record<ScheduleDistributionMode, string> = {
  per_date: "По датам вручную",
  single_day: "В один день",
  serial: "Серия каждые N дней",
};

export function CampaignWizard({
  accounts,
  profiles,
  likedReels,
  projects,
}: Props) {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [campaignName, setCampaignName] = useState<string>(defaultCampaignName);
  const [selectedReelIds, setSelectedReelIds] = useState<number[]>([]);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [timeOfDay, setTimeOfDay] = useState<string>("19:00");
  const [dates, setDates] = useState<string[]>([]);
  const [mode, setMode] = useState<ScheduleDistributionMode>("per_date");
  const [singleDayDate, setSingleDayDate] = useState<string>(todayIso);
  const [singleDayIntervalMin, setSingleDayIntervalMin] = useState<number>(60);
  const [serialStartDate, setSerialStartDate] = useState<string>(todayIso);
  const [serialIntervalDays, setSerialIntervalDays] = useState<number>(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);

  const scheduleValid = useMemo<boolean>(() => {
    if (timeOfDay.length === 0) return false;
    if (mode === "per_date") return dates.length > 0;
    if (mode === "single_day")
      return singleDayDate.length > 0 && singleDayIntervalMin >= 1;
    if (mode === "serial")
      return serialStartDate.length > 0 && serialIntervalDays >= 1;
    return false;
  }, [
    mode,
    timeOfDay,
    dates,
    singleDayDate,
    singleDayIntervalMin,
    serialStartDate,
    serialIntervalDays,
  ]);

  const canAdvance = useMemo<boolean>(() => {
    switch (step) {
      case 1:
        return selectedReelIds.length > 0;
      case 2:
        return selectedAccountIds.length > 0;
      case 3:
        return scheduleValid;
      default:
        return false;
    }
  }, [step, selectedReelIds, selectedAccountIds, scheduleValid]);

  const canSubmit =
    selectedReelIds.length > 0 &&
    selectedAccountIds.length > 0 &&
    scheduleValid &&
    campaignName.trim().length > 0;

  const handleNext = () => {
    if (!canAdvance) return;
    setStep((prev) => ((prev + 1) as Step));
  };

  const handleBack = () => {
    if (step === 1) return;
    setStep((prev) => ((prev - 1) as Step));
  };

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || pendingRef.current) return;
    pendingRef.current = true;
    setError(null);
    setSubmitting(true);
    let campaignId: number | null = null;
    try {
      const response = await schedulerApi.createCampaign({
        name: campaignName.trim(),
        time_of_day: timeOfDay,
        tz: SCHEDULER_TZ,
        reel_artifact_ids: selectedReelIds,
        account_ids: selectedAccountIds,
        mode,
        dates: mode === "per_date" ? dates : undefined,
        single_day_date: mode === "single_day" ? singleDayDate : undefined,
        single_day_interval_min:
          mode === "single_day" ? singleDayIntervalMin : undefined,
        serial_start_date: mode === "serial" ? serialStartDate : undefined,
        serial_interval_days:
          mode === "serial" ? serialIntervalDays : undefined,
      });
      campaignId = response.campaign.id;
      await schedulerApi.approveCampaign(campaignId);
      router.push("/scheduler");
      router.refresh();
    } catch (exc) {
      if (campaignId !== null) {
        await schedulerApi.deleteCampaign(campaignId).catch(() => undefined);
      }
      setError(exc instanceof Error ? exc.message : String(exc));
      setSubmitting(false);
    } finally {
      pendingRef.current = false;
    }
  }, [
    canSubmit,
    campaignName,
    timeOfDay,
    dates,
    mode,
    singleDayDate,
    singleDayIntervalMin,
    serialStartDate,
    serialIntervalDays,
    selectedReelIds,
    selectedAccountIds,
    router,
  ]);

  const accountsById = useMemo(() => {
    const m = new Map<string, PublerAccount>();
    for (const a of accounts) m.set(a.id, a);
    return m;
  }, [accounts]);

  const profilesById = useMemo(() => {
    const m = new Map<string, AccountProfile>();
    for (const p of profiles) m.set(p.publer_account_id, p);
    return m;
  }, [profiles]);

  const reelsById = useMemo(() => {
    const m = new Map<number, LikedReelRef>();
    for (const r of likedReels) m.set(r.id, r);
    return m;
  }, [likedReels]);

  return (
    <div className="flex flex-col gap-6">
      {/* Step indicator */}
      <nav className="surface-card flex flex-wrap gap-2 p-3" aria-label="Шаги">
        {([1, 2, 3, 4] as Step[]).map((n) => {
          const active = n === step;
          const completed = n < step;
          const clickable = n < step;
          return (
            <button
              key={n}
              type="button"
              onClick={() => clickable && setStep(n)}
              disabled={!clickable}
              className={`flex min-w-[140px] flex-1 items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors ${
                active
                  ? "border-[color:var(--gold)] bg-[color:var(--ink-2)]"
                  : completed
                    ? "border-[color:var(--line)] bg-transparent cursor-pointer hover:border-[color:var(--gold)]"
                    : "border-[color:var(--line)] bg-transparent cursor-not-allowed opacity-60"
              }`}
            >
              <span
                className={`mono flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] ${
                  active
                    ? "border-[color:var(--gold)] text-[color:var(--gold)]"
                    : completed
                      ? "border-[color:var(--gold)] bg-[color:var(--gold)] text-[color:var(--ink)]"
                      : "border-[color:var(--line)] text-[color:var(--mute-2)]"
                }`}
              >
                {completed ? "✓" : n}
              </span>
              <span className="flex flex-col">
                <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  шаг {n}
                </span>
                <span
                  className={`text-[13px] ${
                    active
                      ? "text-[color:var(--paper)]"
                      : "text-[color:var(--paper-dim)]"
                  }`}
                >
                  {STEP_LABELS[n]}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      {/* Step body */}
      <section className="flex flex-col gap-4">
        {step === 1 ? (
          <>
            <header className="flex flex-col gap-1">
              <h2 className="display-serif text-2xl text-[color:var(--paper)]">
                Выбери рилсы для кампании
              </h2>
              <p className="text-sm text-[color:var(--text-secondary)]">
                Отмечены только лайкнутые нарезки. Фильтруй по проекту и job.
              </p>
            </header>
            <ReelPicker
              reels={likedReels}
              projects={projects}
              selectedIds={selectedReelIds}
              onSelectionChange={setSelectedReelIds}
            />
          </>
        ) : null}

        {step === 2 ? (
          <>
            <header className="flex flex-col gap-1">
              <h2 className="display-serif text-2xl text-[color:var(--paper)]">
                Куда публиковать
              </h2>
              <p className="text-sm text-[color:var(--text-secondary)]">
                Выбери аккаунты Publer. Для каждого должен быть настроен
                профиль — иначе caption не сгенерируется.
              </p>
            </header>
            <AccountsPicker
              accounts={accounts}
              profiles={profiles}
              selectedIds={selectedAccountIds}
              onSelectionChange={setSelectedAccountIds}
            />
          </>
        ) : null}

        {step === 3 ? (
          <>
            <header className="flex flex-col gap-1">
              <h2 className="display-serif text-2xl text-[color:var(--paper)]">
                Расписание
              </h2>
              <p className="text-sm text-[color:var(--text-secondary)]">
                Одно время для всех аккаунтов. Кампания разложится равномерно
                по выбранным датам.
              </p>
            </header>
            <ScheduleTimeline
              mode={mode}
              onModeChange={setMode}
              timeOfDay={timeOfDay}
              onTimeChange={setTimeOfDay}
              dates={dates}
              onDatesChange={setDates}
              singleDayDate={singleDayDate}
              onSingleDayDateChange={setSingleDayDate}
              singleDayIntervalMin={singleDayIntervalMin}
              onSingleDayIntervalChange={setSingleDayIntervalMin}
              serialStartDate={serialStartDate}
              onSerialStartDateChange={setSerialStartDate}
              serialIntervalDays={serialIntervalDays}
              onSerialIntervalDaysChange={setSerialIntervalDays}
              reelsCount={selectedReelIds.length}
              accountsCount={selectedAccountIds.length}
            />
          </>
        ) : null}

        {step === 4 ? (
          <>
            <header className="flex flex-col gap-1">
              <h2 className="display-serif text-2xl text-[color:var(--paper)]">
                Подтверждение
              </h2>
              <p className="text-sm text-[color:var(--text-secondary)]">
                Проверь параметры — после создания бэкенд сгенерирует caption
                для каждой публикации и запустит воркер.
              </p>
            </header>

            <div className="surface-card flex flex-col gap-4 p-5">
              <label className="flex flex-col gap-1.5">
                <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  Название кампании
                </span>
                <input
                  type="text"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
                />
              </label>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    рилсов
                  </span>
                  <span className="display-serif text-3xl text-[color:var(--paper)]">
                    {selectedReelIds.length}
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    аккаунтов
                  </span>
                  <span className="display-serif text-3xl text-[color:var(--paper)]">
                    {selectedAccountIds.length}
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    публикаций всего
                  </span>
                  <span className="display-serif text-3xl text-[color:var(--paper)]">
                    {selectedReelIds.length * selectedAccountIds.length}
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-1 border-t border-[color:var(--line)] pt-3">
                <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  режим · время · tz
                </span>
                <span className="text-sm text-[color:var(--paper)]">
                  {MODE_LABEL[mode]} · {timeOfDay} · {SCHEDULER_TZ} (+07)
                </span>
                <span className="text-[11px] text-[color:var(--text-secondary)]">
                  {mode === "per_date"
                    ? `${dates.length} ${
                        dates.length === 1 ? "дата" : "дат"
                      }: ${dates.map(formatDateLabel).join(", ")}`
                    : mode === "single_day"
                      ? `В один день ${formatDateLabel(
                          singleDayDate,
                        )}, шаг ${singleDayIntervalMin} мин`
                      : `Серия с ${formatDateLabel(
                          serialStartDate,
                        )}, шаг ${serialIntervalDays} ${
                          serialIntervalDays === 1 ? "день" : "дн."
                        }`}
                </span>
              </div>

              <div className="flex flex-col gap-2 border-t border-[color:var(--line)] pt-3">
                <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  аккаунты
                </span>
                <ul className="flex flex-wrap gap-1.5">
                  {selectedAccountIds.map((id) => {
                    const p = profilesById.get(id);
                    const a = accountsById.get(id);
                    const label = p?.display_name ?? a?.name ?? id;
                    return (
                      <li
                        key={id}
                        className="mono rounded border border-[color:var(--line)] bg-[color:var(--ink)] px-2 py-0.5 text-[11px] text-[color:var(--paper)]"
                      >
                        {label}
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="flex flex-col gap-2 border-t border-[color:var(--line)] pt-3">
                <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  рилсы
                </span>
                <ul className="flex flex-wrap gap-1.5">
                  {selectedReelIds.map((id) => {
                    const r = reelsById.get(id);
                    return (
                      <li
                        key={id}
                        className="mono rounded border border-[color:var(--line)] bg-[color:var(--ink)] px-2 py-0.5 text-[11px] text-[color:var(--paper)]"
                      >
                        #{id}
                        {r ? ` · ${r.job_id.slice(0, 6)}…` : ""}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          </>
        ) : null}
      </section>

      {/* Bottom bar */}
      <div className="sticky bottom-4 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[color:var(--line)] bg-[color:var(--ink)] p-3 shadow-lg">
        <button
          type="button"
          onClick={handleBack}
          disabled={step === 1 || submitting}
          className="rounded-md border border-[color:var(--line)] px-4 py-2 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          ← Назад
        </button>

        <span className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          шаг {step} из 4 · {STEP_LABELS[step]}
        </span>

        {step < 4 ? (
          <button
            type="button"
            onClick={handleNext}
            disabled={!canAdvance || submitting}
            className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            Далее →
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit || submitting}
            className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Создаю…" : "Создать кампанию"}
          </button>
        )}
      </div>
    </div>
  );
}
