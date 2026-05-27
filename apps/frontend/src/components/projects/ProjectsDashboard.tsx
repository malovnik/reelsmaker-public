import { useCallback, useState } from "react";
import { projectsApi, type Project } from "@/lib/api/projects";
import { Button } from "@/components/ui";
import { useConfirm, useToast } from "@/contexts";
import { ProjectsList } from "./ProjectsList";
import { ProjectFormModal } from "./ProjectFormModal";

interface Props {
  initialProjects: Project[];
}

export function ProjectsDashboard({ initialProjects }: Props) {
  const toast = useToast();
  const confirm = useConfirm();
  const [projects, setProjects] = useState<Project[]>(initialProjects);
  const [editing, setEditing] = useState<Project | null>(null);
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setProjects(await projectsApi.listProjects());
    } catch (err) {
      toast.showError(err);
    }
  }, [toast]);

  const handleDelete = useCallback(
    async (project: Project) => {
      const ok = await confirm({
        title: "Удалить проект?",
        description: `Проект «${project.name}» будет удалён. Джобы внутри не удалятся — просто открепятся от проекта.`,
        confirmLabel: "Удалить",
        destructive: true,
      });
      if (!ok) return;
      try {
        await projectsApi.deleteProject(project.id);
        await refresh();
        toast.success("Проект удалён");
      } catch (err) {
        toast.showError(err);
      }
    },
    [confirm, refresh, toast],
  );

  const modalOpen = creating || editing !== null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          // Всего проектов · {projects.length}
        </div>
        <Button variant="primary" size="sm" onClick={() => setCreating(true)}>
          ＋ Новый проект
        </Button>
      </div>

      <ProjectsList
        projects={projects}
        onCreate={() => setCreating(true)}
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
