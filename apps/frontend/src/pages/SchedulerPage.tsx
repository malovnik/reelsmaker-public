import { useLoaderData } from "react-router-dom";
import { schedulerApi } from "@/lib/api";
import { SchedulerDashboard } from "@/components/scheduler/SchedulerDashboard";
import type {
  ConnectionStatus,
  ScheduleCampaign,
} from "@/lib/api/scheduler";

interface SchedulerLoaderData {
  status: ConnectionStatus | null;
  campaigns: ScheduleCampaign[];
  error: string | null;
}

export async function loader(): Promise<SchedulerLoaderData> {
  let status: ConnectionStatus | null = null;
  let campaigns: ScheduleCampaign[] = [];
  let error: string | null = null;
  try {
    status = await schedulerApi.getConnectionStatus();
  } catch (exc) {
    error = exc instanceof Error ? exc.message : String(exc);
  }
  try {
    campaigns = await schedulerApi.listCampaigns();
  } catch (exc) {
    if (!error) error = exc instanceof Error ? exc.message : String(exc);
  }
  return { status, campaigns, error };
}

export default function SchedulerPage() {
  const { status, campaigns, error } = useLoaderData() as SchedulerLoaderData;
  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Шедулер
        </h1>
        <p className="page-subtitle">
          Планирование публикаций рилсов через Publer. Подключает Instagram и
          YouTube-аккаунты из одного рабочего места, собирает кампании и
          заливает посты по расписанию.
        </p>
      </header>

      <SchedulerDashboard
        initialStatus={status}
        initialCampaigns={campaigns}
        initialError={error}
      />
      </div>
    </main>
  );
}
