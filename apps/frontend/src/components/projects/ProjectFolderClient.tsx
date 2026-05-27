import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { projectsApi, type ProjectDetail } from "@/lib/api/projects";
import { schedulerApi, type LikedReelRef } from "@/lib/api/scheduler";
import { Skeleton } from "@/components/ui";
import { useToast } from "@/contexts";
import { humanizeError } from "@/lib/humanizeError";

interface Props {
  projectId: number;
}

function buildReelFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2) {
    return `/api/v1/files/${jobId}/reels/${encodeURIComponent(relativePath)}`;
  }
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}

/**
 * Папка проекта: шапка + сетка сохранённых рилсов 9:16. Загрузка/ошибка/пусто —
 * честные состояния. Сетевые сбои проходят через humanizeError + тост.
 */
export function ProjectFolderClient({ projectId }: Props) {
  const toast = useToast();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [reels, setReels] = useState<LikedReelRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(projectId)) {
      setError("Ссылка на проект битая — проверьте адрес.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [detail, liked] = await Promise.all([
          projectsApi.getProject(projectId),
          schedulerApi.listLikedReels({ projectId }),
        ]);
        if (cancelled) return;
        setProject(detail);
        setReels(liked);
      } catch (err) {
        if (cancelled) return;
        const human = humanizeError(err);
        setError(`${human.title}. ${human.detail}`);
        toast.showError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, toast]);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <Link
          to="/projects"
          className="mono w-fit text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)] transition-colors hover:text-[var(--paper)]"
        >
          ← Проекты
        </Link>
        <div className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--copper)]">
          // Папка проекта
        </div>
        <h1 className="display-serif text-2xl leading-tight text-[var(--paper)] md:text-3xl">
          {project ? project.name : "Папка проекта"}
        </h1>
        <p className="text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
          {project
            ? `${project.jobs.length} ${project.jobs.length === 1 ? "джоб" : "джобов"} · ${reels.length} сохранённых рилсов`
            : "Сохранённые в лайки рилсы проекта — готовый пул для публикации."}
        </p>
      </header>

      {error ? (
        <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-4 text-[0.875rem] text-[var(--danger)]">
          {error}
        </div>
      ) : loading ? (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <li key={i}>
              <Skeleton className="aspect-[9/16] w-full" />
            </li>
          ))}
        </ul>
      ) : reels.length === 0 ? (
        <div className="flex flex-col items-center gap-2 border border-[var(--line-soft)] bg-[var(--ink-2)] p-10 text-center">
          <div className="display-serif text-xl text-[var(--paper)]">
            Сохранённых рилсов пока нет
          </div>
          <p className="max-w-md text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
            Отлайкайте рилсы в нарезках проекта — они появятся здесь и попадут в пул
            для планировщика.
          </p>
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 lg:gap-6">
          {reels.map((reel) => {
            const reelId = String(reel.meta?.reel_id ?? reel.id);
            const url = buildReelFileUrl(reel.job_id, reel.path);
            return (
              <li
                key={reel.id}
                className="flex flex-col gap-2 border border-[var(--line-soft)] bg-[var(--ink-2)] p-2"
              >
                <div className="aspect-[9/16] bg-[var(--kuro)]">
                  <video
                    src={url}
                    controls
                    playsInline
                    preload="metadata"
                    className="size-full object-contain"
                  />
                </div>
                <div className="flex items-center justify-between px-1">
                  <span className="mono text-[0.6875rem] text-[var(--mute-2)]">{reelId}</span>
                  <Link
                    to={`/jobs/${reel.job_id}/reels/${reel.id}`}
                    className="mono text-[0.6875rem] uppercase tracking-[0.1em] text-[var(--gold)] transition-colors hover:text-[var(--kogane)]"
                  >
                    Открыть
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
