import { useLoaderData, type LoaderFunctionArgs } from "react-router-dom";
import { api, ApiError, type ArtifactRead, type JobRead } from "@/lib/api";
import { TinderClient } from "@/components/job/TinderClient";
import { notFound } from "@/lib/router-compat";

interface TinderLoaderData {
  job: JobRead;
  reels: ArtifactRead[];
}

export async function loader({
  params,
}: LoaderFunctionArgs): Promise<TinderLoaderData> {
  const id = params.id;
  if (!id) notFound();
  try {
    const job = await api.getJob(id);
    const artifacts = await api
      .listArtifacts(id)
      .catch(() => [] as ArtifactRead[]);
    const reels = artifacts.filter((a) => a.kind === "reel_output");
    return { job, reels };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export default function JobTinderPage() {
  const { job, reels } = useLoaderData() as TinderLoaderData;
  return <TinderClient job={job} initialReels={reels} />;
}
