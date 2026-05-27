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
import { Button } from "@/components/ui";
import { useToast } from "@/contexts";
import { ReelPicker } from "./ReelPicker";
import { AccountsPicker } from "./AccountsPicker";
import { ScheduleTimeline } from "./ScheduleTimeline";
import { WizardStepper, WIZARD_STEP_LABELS, type WizardStep } from "./WizardStepper";
import { WizardSummary } from "./WizardSummary";

interface Props {
  accounts: PublerAccount[];
  profiles: AccountProfile[];
  likedReels: LikedReelRef[];
  projects: Project[];
}

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

const STEP_HEADER: Record<WizardStep, { title: string; desc: string }> = {
  1: {
    title: "Выберите рилсы для кампании",
    desc: "Доступны только сохранённые в лайки нарезки. Отфильтруйте по проекту или джобу.",
  },
  2: {
    title: "Куда публикуем",
    desc: "Отметьте аккаунты Publer. Для каждого нужен профиль — иначе подпись не соберётся.",
  },
  3: {
    title: "Расписание",
    desc: "Одно время для всех аккаунтов. Публикации разложатся равномерно по выбранным датам.",
  },
  4: {
    title: "Подтверждение",
    desc: "Проверьте параметры — после создания соберём подпись для каждой публикации и запустим доставку.",
  },
};

export function CampaignWizard({ accounts, profiles, likedReels, projects }: Props) {
  const router = useRouter();
  const toast = useToast();
  const [step, setStep] = useState<WizardStep>(1);
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
  const pendingRef = useRef(false);

  const scheduleValid = useMemo<boolean>(() => {
    if (timeOfDay.length === 0) return false;
    if (mode === "per_date") return dates.length > 0;
    if (mode === "single_day") return singleDayDate.length > 0 && singleDayIntervalMin >= 1;
    if (mode === "serial") return serialStartDate.length > 0 && serialIntervalDays >= 1;
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
    if (canAdvance) setStep((prev) => (prev + 1) as WizardStep);
  };
  const handleBack = () => {
    if (step > 1) setStep((prev) => (prev - 1) as WizardStep);
  };

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || pendingRef.current) return;
    pendingRef.current = true;
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
        single_day_interval_min: mode === "single_day" ? singleDayIntervalMin : undefined,
        serial_start_date: mode === "serial" ? serialStartDate : undefined,
        serial_interval_days: mode === "serial" ? serialIntervalDays : undefined,
      });
      campaignId = response.campaign.id;
      await schedulerApi.approveCampaign(campaignId);
      toast.success("Кампания создана и запущена");
      router.push("/scheduler");
      router.refresh();
    } catch (err) {
      if (campaignId !== null) {
        await schedulerApi.deleteCampaign(campaignId).catch(() => undefined);
      }
      toast.showError(err);
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
    toast,
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

  const header = STEP_HEADER[step];

  return (
    <div className="flex flex-col gap-8">
      <WizardStepper current={step} onGoto={setStep} />

      <section className="flex flex-col gap-5">
        <header className="flex flex-col gap-1.5">
          <h2 className="display-serif text-xl text-[var(--paper)] md:text-2xl">
            {header.title}
          </h2>
          <p className="text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">{header.desc}</p>
        </header>

        {step === 1 ? (
          <ReelPicker
            reels={likedReels}
            projects={projects}
            selectedIds={selectedReelIds}
            onSelectionChange={setSelectedReelIds}
          />
        ) : null}

        {step === 2 ? (
          <AccountsPicker
            accounts={accounts}
            profiles={profiles}
            selectedIds={selectedAccountIds}
            onSelectionChange={setSelectedAccountIds}
          />
        ) : null}

        {step === 3 ? (
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
        ) : null}

        {step === 4 ? (
          <WizardSummary
            campaignName={campaignName}
            onNameChange={setCampaignName}
            selectedReelIds={selectedReelIds}
            selectedAccountIds={selectedAccountIds}
            mode={mode}
            timeOfDay={timeOfDay}
            dates={dates}
            singleDayDate={singleDayDate}
            singleDayIntervalMin={singleDayIntervalMin}
            serialStartDate={serialStartDate}
            serialIntervalDays={serialIntervalDays}
            accountsById={accountsById}
            profilesById={profilesById}
            reelsById={reelsById}
          />
        ) : null}
      </section>

      <div className="sticky bottom-4 z-20 flex flex-wrap items-center justify-between gap-3 border border-[var(--line)] bg-[var(--ink)] p-3">
        <Button variant="secondary" onClick={handleBack} disabled={step === 1 || submitting}>
          ← Назад
        </Button>
        <span className="mono hidden text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)] sm:inline">
          Шаг {step} из 4 · {WIZARD_STEP_LABELS[step]}
        </span>
        {step < 4 ? (
          <Button variant="primary" onClick={handleNext} disabled={!canAdvance || submitting}>
            Дальше →
          </Button>
        ) : (
          <Button variant="primary" onClick={handleSubmit} loading={submitting} disabled={!canSubmit}>
            Создать кампанию
          </Button>
        )}
      </div>
    </div>
  );
}
