
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type JobRead,
  type ModelsInfo,
  type PostProductionPreset,
  type ProfileMaskRead,
  type SubtitleStylePreset,
} from "@/lib/api";
import { UploadWizard } from "./upload/UploadWizard";
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

  return (
    <div className="flex flex-col gap-12">
      <DashboardHero jobs={jobs} />

      <section className="surface-card p-6">
        <div className="divider mb-6">новая нарезка</div>
        <UploadWizard
          models={models}
          subtitlePresets={subtitlePresets}
          postProductionPresets={postProductionPresets}
          profileMasks={profileMasks}
          defaultUseSourceForRender={defaultUseSourceForRender}
          onJobCreated={refreshJobs}
        />
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
