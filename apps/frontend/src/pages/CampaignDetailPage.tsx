import { useLoaderData, type LoaderFunctionArgs } from "react-router-dom";
import { schedulerApi } from "@/lib/api";
import { CampaignDetailClient } from "@/components/scheduler/CampaignDetailClient";
import type { CampaignDetail } from "@/lib/api/scheduler";
import { notFound } from "@/lib/router-compat";

export async function loader({
  params,
}: LoaderFunctionArgs): Promise<CampaignDetail> {
  const idStr = params.id;
  const id = Number.parseInt(idStr ?? "", 10);
  if (!Number.isFinite(id) || id <= 0) notFound();
  try {
    return await schedulerApi.getCampaign(id);
  } catch {
    notFound();
  }
}

export default function CampaignDetailPage() {
  const campaign = useLoaderData() as CampaignDetail;
  return (
    <main className="page-shell">
      <CampaignDetailClient initialCampaign={campaign} />
    </main>
  );
}
