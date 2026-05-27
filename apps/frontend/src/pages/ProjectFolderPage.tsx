import { useParams } from "react-router-dom";
import { ProjectFolderClient } from "@/components/projects/ProjectFolderClient";

/**
 * Экран папки проекта (`/projects/:id/folder`). Тонкая обёртка-страница:
 * парсит :id и делегирует редизайн-клиенту. Error Boundary вокруг лениво-роута
 * стоит в router.tsx.
 */
export default function ProjectFolderPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ? Number(id) : NaN;

  return (
    <main className="page-shell">
      <ProjectFolderClient projectId={projectId} />
    </main>
  );
}
