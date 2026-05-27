import { useLoaderData } from "react-router-dom";
import { projectsApi, type Project } from "@/lib/api/projects";
import { ProjectsDashboard } from "@/components/projects/ProjectsDashboard";

interface ProjectsLoaderData {
  initialProjects: Project[];
  error: string | null;
}

export async function loader(): Promise<ProjectsLoaderData> {
  try {
    const initialProjects = await projectsApi.listProjects();
    return { initialProjects, error: null };
  } catch (exc) {
    return {
      initialProjects: [],
      error: exc instanceof Error ? exc.message : String(exc),
    };
  }
}

export default function ProjectsPage() {
  const { initialProjects, error } = useLoaderData() as ProjectsLoaderData;

  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Проекты
        </h1>
        <p className="page-subtitle">
          Папки для группировки джобов. Шедулер берёт из выбранного проекта
          только лайкнутые рилсы и собирает из них кампанию публикаций.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Не удалось загрузить проекты: {error}
        </div>
      ) : (
        <ProjectsDashboard initialProjects={initialProjects} />
      )}
      </div>
    </main>
  );
}
