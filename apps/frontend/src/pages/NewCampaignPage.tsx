import { Link, useLoaderData } from "react-router-dom";
import { schedulerApi } from "@/lib/api";
import { projectsApi, type Project } from "@/lib/api/projects";
import { CampaignWizard } from "@/components/scheduler/CampaignWizard";
import type {
  AccountProfile,
  LikedReelRef,
  PublerAccount,
} from "@/lib/api/scheduler";

interface NewCampaignLoaderData {
  accounts: PublerAccount[];
  profiles: AccountProfile[];
  liked: LikedReelRef[];
  projects: Project[];
  error: string | null;
}

export async function loader(): Promise<NewCampaignLoaderData> {
  try {
    const [accounts, profiles, liked, projects] = await Promise.all([
      schedulerApi.listPublerAccounts(),
      schedulerApi.listProfiles(),
      schedulerApi.listLikedReels({ limit: 500 }),
      projectsApi.listProjects(),
    ]);
    return { accounts, profiles, liked, projects, error: null };
  } catch (exc) {
    return {
      accounts: [],
      profiles: [],
      liked: [],
      projects: [],
      error: exc instanceof Error ? exc.message : String(exc),
    };
  }
}

export default function NewCampaignPage() {
  const { accounts, profiles, liked, projects, error } =
    useLoaderData() as NewCampaignLoaderData;

  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          <Link
            to="/scheduler"
            className="transition-colors hover:text-[color:var(--paper)]"
          >
            шедулер
          </Link>{" "}
          · новая кампания
        </div>
        <h1 className="page-h1">
          Новая кампания
        </h1>
        <p className="page-subtitle">
          Четыре шага: выбор рилсов, назначений, расписания и подтверждение.
          После создания Publer получит задания — caption сгенерируется
          автоматически по профилю аккаунта.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : (
        <CampaignWizard
          accounts={accounts}
          profiles={profiles}
          likedReels={liked}
          projects={projects}
        />
      )}
      </div>
    </main>
  );
}
