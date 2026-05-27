
import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { api, type ArtifactRead, type JobRead } from "@/lib/api";
import { useJobSse } from "@/lib/sse";
import { JobHero } from "@/components/job/JobHero";
import { PipelineTimeline } from "@/components/job/PipelineTimeline";
import { ReelGrid } from "@/components/job/ReelGrid";
import { HeatmapBar } from "@/components/job/HeatmapBar";
import { ArtifactsAccordion } from "@/components/job/ArtifactsAccordion";

interface Props {
  initialJob: JobRead;
  initialArtifacts: ArtifactRead[];
}

export function JobDetailClient({ initialJob, initialArtifacts }: Props) {
  const [job, setJob] = useState<JobRead>(initialJob);
  const [artifacts, setArtifacts] = useState<ArtifactRead[]>(initialArtifacts);
  const isActive = job.status === "running" || job.status === "pending";
  const sse = useJobSse(isActive ? job.id : null);

  useEffect(() => {
    if (sse.finalStatus === "done" || sse.finalStatus === "error") {
      (async () => {
        try {
          const [freshJob, freshArtifacts] = await Promise.all([
            api.getJob(job.id),
            api.listArtifacts(job.id),
          ]);
          setJob(freshJob);
          setArtifacts(freshArtifacts);
        } catch {
          // ignore — UI останется в текущем состоянии
        }
      })();
    }
  }, [sse.finalStatus, job.id]);

  const currentProgress = sse.lastEvent?.progress ?? job.progress;
  const currentMessage = sse.lastEvent?.message ?? job.message ?? "";
  const currentStage =
    sse.lastEvent?.stage ??
    job.current_stage ??
    (job.status === "done" ? "done" : "ingest");

  const cacheState = sse.lastEvent?.transcript_cache ?? null;
  const wordCount = sse.lastEvent?.cached_word_count ?? sse.lastEvent?.word_count;
  const wpm = sse.lastEvent?.cached_wpm;
  const videoHash = sse.lastEvent?.video_hash;

  const reels = useMemo(
    () => artifacts.filter((a) => a.kind === "reel_output"),
    [artifacts],
  );

  const auxiliaryArtifacts = useMemo(
    () => artifacts.filter((a) => a.kind !== "reel_output"),
    [artifacts],
  );

  return (
    <div className="flex flex-col gap-8">
      <JobHero
        job={job}
        progress={currentProgress}
        cacheState={cacheState}
        wordCount={wordCount}
        wpm={wpm}
        videoHash={videoHash}
      />

      {reels.length > 0 && (
        <div className="-mt-2 flex">
          <Link
            to={`/jobs/${job.id}/tinder`}
            className="inline-flex items-center gap-2 rounded-full bg-[color:var(--accent-primary)] px-4 py-2 text-xs font-semibold text-[color:var(--accent-on-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[color:var(--accent-primary-hover)]"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            Режим Tinder · размечать по одному
          </Link>
        </div>
      )}

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div className="surface-card p-5">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
            Этапы обработки
          </h2>
          <PipelineTimeline
            currentStage={currentStage}
            status={job.status}
            progress={currentProgress}
            message={currentMessage}
            stageDurations={job.stage_durations}
          />
        </div>

        <div className="flex flex-col gap-5">
          {reels.length > 0 && <HeatmapBar job={job} reels={reels} />}
          {reels.length > 0 ? (
            <ReelGrid
              jobId={job.id}
              reels={reels}
              onChange={(nextReels) => {
                const otherKinds = artifacts.filter(
                  (a) => a.kind !== "reel_output",
                );
                setArtifacts([...otherKinds, ...nextReels]);
              }}
            />
          ) : (
            <div className="surface-card flex flex-col items-center justify-center gap-2 border-dashed p-10 text-center">
              <p className="text-sm text-[color:var(--text-secondary)]">
                {job.status === "error"
                  ? "Обработка остановилась с ошибкой — рилсы не готовы."
                  : job.status === "done"
                    ? "Пайплайн завершился, но рилсы не нашлись в артефактах."
                    : "Ещё идёт обработка — рилсы появятся на этапе «Сборка рилсов»."}
              </p>
            </div>
          )}

          <ArtifactsAccordion jobId={job.id} artifacts={auxiliaryArtifacts} />
        </div>
      </section>
    </div>
  );
}
