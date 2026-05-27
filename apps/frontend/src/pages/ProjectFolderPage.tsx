import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { projectsApi, type ProjectDetail } from "@/lib/api/projects";
import { schedulerApi, type LikedReelRef } from "@/lib/api/scheduler";

/**
 * R2.2 (FL-07) — экран папки проекта: список сохранённых (лайкнутых) рилсов.
 * Минимальная нередизайненная реализация — финальный дизайн в Phase 9.
 * Маршрут (добавляет FE-3): `/projects/:id/folder`.
 */
function buildReelFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2) {
    return `/api/v1/files/${jobId}/reels/${encodeURIComponent(relativePath)}`;
  }
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}

export default function ProjectFolderPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ? Number(id) : NaN;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [reels, setReels] = useState<LikedReelRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(projectId)) {
      setError("Некорректный идентификатор проекта");
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
      } catch (exc) {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
        <header className="flex flex-col gap-2">
          <Link
            to="/projects"
            className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
          >
            ← к проектам
          </Link>
          <h1 className="page-h1">
            {project ? project.name : "Папка проекта"}
          </h1>
          <p className="page-subtitle">
            Сохранённые (лайкнутые) рилсы проекта — готовый pool для публикации.
          </p>
        </header>

        {error ? (
          <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
            Не удалось загрузить папку проекта: {error}
          </div>
        ) : loading ? (
          <div className="text-sm text-[color:var(--text-muted)]">Загружаю…</div>
        ) : reels.length === 0 ? (
          <div className="surface-card p-10 text-center text-sm text-[color:var(--text-secondary)]">
            В этом проекте пока нет сохранённых рилсов. Отлайкай рилсы в нарезках
            проекта — они появятся здесь.
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {reels.map((reel) => {
              const reelId = String(reel.meta?.reel_id ?? reel.id);
              const url = buildReelFileUrl(reel.job_id, reel.path);
              return (
                <li
                  key={reel.id}
                  className="surface-card flex flex-col gap-2 overflow-hidden p-3"
                >
                  <div className="aspect-[9/16] bg-black">
                    <video
                      src={url}
                      controls
                      playsInline
                      preload="metadata"
                      className="size-full object-contain"
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="mono text-[color:var(--text-secondary)]">
                      {reelId}
                    </span>
                    <Link
                      to={`/jobs/${reel.job_id}/reels/${reel.id}`}
                      className="text-[color:var(--text-muted)] transition-colors hover:text-[color:var(--text-primary)]"
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
    </main>
  );
}
