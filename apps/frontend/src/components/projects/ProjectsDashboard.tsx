
import { useCallback, useState } from "react";
import { projectsApi, type Project } from "@/lib/api/projects";
import { ProjectsList } from "./ProjectsList";
import { ProjectFormModal } from "./ProjectFormModal";

interface Props {
  initialProjects: Project[];
}

export function ProjectsDashboard({ initialProjects }: Props) {
  const [projects, setProjects] = useState<Project[]>(initialProjects);
  const [editing, setEditing] = useState<Project | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fresh = await projectsApi.listProjects();
      setProjects(fresh);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  const handleDelete = useCallback(
    async (project: Project) => {
      if (
        !confirm(
          `Удалить проект «${project.name}»? Джобы внутри останутся, связь со` +
            " проектом снимется.",
        )
      ) {
        return;
      }
      try {
        await projectsApi.deleteProject(project.id);
        await refresh();
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    },
    [refresh],
  );

  const modalOpen = creating || editing !== null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          всего проектов · {projects.length}
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="btn btn-primary"
        >
          + Новый проект
        </button>
      </div>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      <ProjectsList
        projects={projects}
        onEdit={(p) => setEditing(p)}
        onDelete={handleDelete}
      />

      <ProjectFormModal
        open={modalOpen}
        project={editing}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onSaved={async () => {
          setCreating(false);
          setEditing(null);
          await refresh();
        }}
      />
    </div>
  );
}
