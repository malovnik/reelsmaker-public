import { useLoaderData, type LoaderFunctionArgs } from "react-router-dom";
import { api, ApiError, type ArtifactRead, type JobRead } from "@/lib/api";
import { JobDetailClient } from "@/components/JobDetailClient";
import { notFound } from "@/lib/router-compat";

interface JobLoaderData {
  job: JobRead;
  artifacts: ArtifactRead[];
}

export async function loader({
  params,
}: LoaderFunctionArgs): Promise<JobLoaderData> {
  const id = params.id;
  if (!id) notFound();
  try {
    const job = await api.getJob(id);
    const artifacts = await api
      .listArtifacts(id)
      .catch(() => [] as ArtifactRead[]);
    return { job, artifacts };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export default function JobDetailPage() {
  const { job, artifacts } = useLoaderData() as JobLoaderData;
  return (
    <main className="page-shell">
      <JobDetailClient initialJob={job} initialArtifacts={artifacts} />
    </main>
  );
}
