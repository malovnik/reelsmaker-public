import { useLoaderData, type LoaderFunctionArgs } from "react-router-dom";
import { api, ApiError, type ArtifactRead, type JobRead } from "@/lib/api";
import { ClipDetailClient } from "@/components/job/ClipDetailClient";
import { notFound } from "@/lib/router-compat";

interface ClipLoaderData {
  job: JobRead;
  reel: ArtifactRead;
  siblings: ArtifactRead[];
}

export async function loader({
  params,
}: LoaderFunctionArgs): Promise<ClipLoaderData> {
  const { id, reelId } = params;
  if (!id || !reelId) notFound();
  try {
    const job = await api.getJob(id);
    const artifacts = await api
      .listArtifacts(id)
      .catch(() => [] as ArtifactRead[]);
    const reels = artifacts.filter((a) => a.kind === "reel_output");
    const reel = reels.find((r) => String(r.id) === reelId);
    if (!reel) notFound();
    return { job, reel, siblings: reels };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export default function ClipDetailPage() {
  const { job, reel, siblings } = useLoaderData() as ClipLoaderData;
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
      <ClipDetailClient job={job} reel={reel} siblings={siblings} />
    </main>
  );
}
