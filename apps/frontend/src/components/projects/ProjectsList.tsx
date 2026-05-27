
import { Link } from "react-router-dom";
import type { Project } from "@/lib/api/projects";

interface Props {
  projects: Project[];
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
}

const FALLBACK_COLOR = "#6366f1";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function ProjectsList({ projects, onEdit, onDelete }: Props) {
  if (projects.length === 0) {
    return (
      <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
        <div className="display-serif text-2xl text-[color:var(--paper)]">
          Пока нет ни одного проекта
        </div>
        <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
          Создай первый проект — он станет папкой для джобов. В шедулере
          выбираешь проект и получаешь pool лайкнутых рилсов из него.
        </p>
      </div>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {projects.map((p) => {
        const color = p.color && p.color.trim() ? p.color : FALLBACK_COLOR;
        return (
          <li
            key={p.id}
            className="surface-card flex flex-col gap-3 p-5"
            style={{ borderLeft: `4px solid ${color}` }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 flex-col gap-1">
                <div className="display-serif truncate text-xl text-[color:var(--paper)]">
                  {p.name}
                </div>
                <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  id · {p.id} · создан {formatDate(p.created_at)}
                </div>
              </div>
              <span
                aria-label="Цвет проекта"
                className="h-5 w-5 shrink-0 rounded-full border border-[color:var(--line)]"
                style={{ backgroundColor: color }}
              />
            </div>

            <p className="line-clamp-3 min-h-[3em] text-sm text-[color:var(--text-secondary)]">
              {p.description || "Без описания"}
            </p>

            <div className="mt-auto flex items-center gap-2 pt-2">
              <Link
                to={`/projects/${p.id}/folder`}
                className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
              >
                Открыть папку
              </Link>
              <button
                type="button"
                onClick={() => onEdit(p)}
                className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
              >
                Редактировать
              </button>
              <button
                type="button"
                onClick={() => onDelete(p)}
                className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)]"
              >
                Удалить
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
