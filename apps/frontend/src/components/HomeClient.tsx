
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type JobRead,
  type ModelsInfo,
  type PostProductionPreset,
  type ProfileMaskRead,
  type SubtitleStylePreset,
} from "@/lib/api";
import { useUiMode, WizardStateProvider } from "@/contexts";
import { UploadWizard } from "./upload/UploadWizard";
import { GuidedFlow } from "./upload/guided/GuidedFlow";
import { JobList } from "./JobList";
import { DashboardHero } from "./dashboard/DashboardHero";

interface Props {
  models: ModelsInfo;
  initialJobs: JobRead[];
  subtitlePresets: SubtitleStylePreset[];
  postProductionPresets: PostProductionPreset[];
  profileMasks: ProfileMaskRead[];
  defaultUseSourceForRender: boolean;
}

export function HomeClient({
  models,
  initialJobs,
  subtitlePresets,
  postProductionPresets,
  profileMasks,
  defaultUseSourceForRender,
}: Props) {
  const [jobs, setJobs] = useState<JobRead[]>(initialJobs);

  const refreshJobs = useCallback(async () => {
    try {
      const fresh = await api.listJobs(50);
      setJobs(fresh);
    } catch {
      // невидимая ошибка polling — не ломаем UI
    }
  }, []);

  // Polling только пока есть активные jobs. Ставим зависимость на булев
  // флаг, а не на массив `jobs` — иначе useEffect cleanup→reschedule
  // выполняется на каждом успешном poll'е, создавая лишние setInterval.
  const hasActiveJobs = jobs.some(
    (j) => j.status === "running" || j.status === "pending",
  );
  useEffect(() => {
    if (!hasActiveJobs) return;
    const interval = setInterval(refreshJobs, 5000);
    return () => clearInterval(interval);
  }, [hasActiveJobs, refreshJobs]);

  // R2.5 (FL-06): когда нет активных джобов, а последняя нарезка готова —
  // показываем явный крупный CTA к результату, а не мелкую ссылку в списке.
  const latestDoneJob = useMemo(() => {
    const done = jobs
      .filter((j) => j.status === "done")
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    return done[0] ?? null;
  }, [jobs]);

  return (
    <div className="flex flex-col gap-12">
      <DashboardHero jobs={jobs} />

      {!hasActiveJobs && latestDoneJob && (
        <section className="surface-card flex flex-col items-start gap-4 border-l-4 border-[color:var(--success)] p-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--success)]">
              нарезка готова
            </span>
            <span className="display-serif text-xl text-[color:var(--text-primary)]">
              {latestDoneJob.display_name ?? latestDoneJob.source_filename}
            </span>
            <span className="text-sm text-[color:var(--text-secondary)]">
              Рилсы собраны — посмотри результат и опубликуй.
            </span>
          </div>
          <Link
            to={`/jobs/${latestDoneJob.id}`}
            className="btn btn-primary shrink-0 px-6 py-3 text-base"
          >
            Смотреть рилсы
          </Link>
        </section>
      )}

      <section className="surface-card p-6">
        {/* WizardStateProvider смонтирован НАД обоими режимами: guided и
            expert читают один источник состояния. Переключение режима
            (useUiMode) не размонтирует store → File, project_id и все
            выборы сохраняются (lossless switch). */}
        <WizardStateProvider
          models={models}
          subtitlePresets={subtitlePresets}
          postProductionPresets={postProductionPresets}
          defaultUseSourceForRender={defaultUseSourceForRender}
          onJobCreated={refreshJobs}
        >
          <StudioSwitch
            models={models}
            subtitlePresets={subtitlePresets}
            postProductionPresets={postProductionPresets}
            profileMasks={profileMasks}
          />
        </WizardStateProvider>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="divider flex-1">мои нарезки</div>
          <button
            onClick={refreshJobs}
            className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
            type="button"
          >
            Обновить
          </button>
        </div>
        <JobList jobs={jobs} />
      </section>
    </div>
  );
}

interface StudioSwitchProps {
  models: ModelsInfo;
  subtitlePresets: SubtitleStylePreset[];
  postProductionPresets: PostProductionPreset[];
  profileMasks: ProfileMaskRead[];
}

/**
 * Переключатель режима Студии. Сегмент-контрол сверху (Пошаговый/Эксперт) +
 * сам режим. Оба читают общий WizardStateProvider выше — данные не теряются
 * при переключении. Сегмент-контрол управляет глобальным useUiMode (persist).
 */
function StudioSwitch({
  models,
  subtitlePresets,
  postProductionPresets,
  profileMasks,
}: StudioSwitchProps) {
  const { mode, setMode, isGuided } = useUiMode();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div className="divider flex-1">новая нарезка</div>
        <div
          role="tablist"
          aria-label="Режим студии"
          className="flex shrink-0 border border-[color:var(--line)]"
        >
          <button
            type="button"
            role="tab"
            aria-selected={isGuided}
            onClick={() => setMode("guided")}
            className={`mono px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] transition-colors ${
              isGuided
                ? "bg-[color:var(--gold)] text-[color:var(--ink)]"
                : "text-[color:var(--mute-2)] hover:text-[color:var(--paper)]"
            }`}
          >
            Пошаговый
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "expert"}
            onClick={() => setMode("expert")}
            className={`mono border-l border-[color:var(--line)] px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] transition-colors ${
              mode === "expert"
                ? "bg-[color:var(--gold)] text-[color:var(--ink)]"
                : "text-[color:var(--mute-2)] hover:text-[color:var(--paper)]"
            }`}
          >
            Эксперт
          </button>
        </div>
      </div>

      {isGuided ? (
        <GuidedFlow
          models={models}
          subtitlePresets={subtitlePresets}
          profileMasks={profileMasks}
          onOpenExpert={() => setMode("expert")}
        />
      ) : (
        <UploadWizard
          models={models}
          subtitlePresets={subtitlePresets}
          postProductionPresets={postProductionPresets}
          profileMasks={profileMasks}
          onOpenGuided={() => setMode("guided")}
        />
      )}
    </div>
  );
}
