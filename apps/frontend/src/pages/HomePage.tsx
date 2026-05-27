import { useLoaderData } from "react-router-dom";
import {
  api,
  type HealthResponse,
  type JobRead,
  type ModelsInfo,
  type PerformanceSettings,
  type PostProductionPreset,
  type ProfileMaskRead,
  type SubtitleStylePreset,
} from "@/lib/api";
import { HomeClient } from "@/components/HomeClient";

interface HomeLoaderData {
  health: HealthResponse | null;
  models: ModelsInfo | null;
  jobs: JobRead[];
  subtitlePresets: SubtitleStylePreset[];
  postProductionPresets: PostProductionPreset[];
  performance: PerformanceSettings | null;
  profileMasks: ProfileMaskRead[];
}

export async function loader(): Promise<HomeLoaderData> {
  const [
    health,
    models,
    jobs,
    subtitlePresets,
    postProductionPresets,
    performance,
    profileMasks,
  ] = await Promise.all([
    api.health().catch(() => null as HealthResponse | null),
    api.models().catch(() => null as ModelsInfo | null),
    api.listJobs(50).catch(() => [] as JobRead[]),
    api.listSubtitlePresets().catch(() => [] as SubtitleStylePreset[]),
    api
      .listPostProductionPresets()
      .catch(() => [] as PostProductionPreset[]),
    api.getPerformanceSettings().catch(() => null),
    api.listVisionProfiles().catch(() => [] as ProfileMaskRead[]),
  ]);
  return {
    health,
    models,
    jobs,
    subtitlePresets,
    postProductionPresets,
    performance,
    profileMasks,
  };
}

export default function HomePage() {
  const data = useLoaderData() as HomeLoaderData;

  if (!data.models) {
    return (
      <main className="page-shell !max-w-3xl">
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Сервер Reelibra не отвечает. Запусти{" "}
          <code className="font-mono">./run.sh</code> в папке проекта — он
          поднимет API на порту 8000.
        </div>
        {data.health ? (
          <div className="text-xs text-[color:var(--text-muted)]">
            health: {JSON.stringify(data.health)}
          </div>
        ) : null}
      </main>
    );
  }

  return (
    <main className="page-shell">
      <HomeClient
        models={data.models}
        initialJobs={data.jobs}
        subtitlePresets={data.subtitlePresets}
        postProductionPresets={data.postProductionPresets}
        profileMasks={data.profileMasks}
        defaultUseSourceForRender={
          data.performance?.default_use_source_for_render ?? false
        }
      />
    </main>
  );
}
