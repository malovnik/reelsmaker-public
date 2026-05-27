import { Link } from "react-router-dom";
import type { Project } from "@/lib/api/projects";
import { Button, Card } from "@/components/ui";

interface Props {
  projects: Project[];
  onCreate: () => void;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
}

const FALLBACK_COLOR = "var(--gold)";

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

/** Сетка карточек проектов. Действия видимы всегда, тач-таргет ≥44px. */
export function ProjectsList({ projects, onCreate, onEdit, onDelete }: Props) {
  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 border border-[var(--line-soft)] bg-[var(--ink-2)] p-10 text-center">
        <div className="display-serif text-xl text-[var(--paper)]">Проектов пока нет</div>
        <p className="max-w-md text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
          Создайте первый — сгруппируете джобы по клиентам или темам, а в планировщике
          возьмёте из проекта готовый пул лайкнутых рилсов.
        </p>
        <Button variant="primary" className="mt-2" onClick={onCreate}>
          ＋ Новый проект
        </Button>
      </div>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6">
      {projects.map((p) => {
        const color = p.color && p.color.trim() ? p.color : FALLBACK_COLOR;
        return (
          <li key={p.id} className="flex">
            <Card
              interactive
              className="flex w-full flex-col gap-4 border-l-2"
              style={{ borderLeftColor: color }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-1">
                  <h3 className="display-serif truncate text-lg text-[var(--paper)]">
                    {p.name}
                  </h3>
                  <div className="mono text-[0.6875rem] text-[var(--mute-2)]">
                    создан {formatDate(p.created_at)}
                  </div>
                </div>
                <span
                  aria-hidden="true"
                  className="size-4 shrink-0"
                  style={{ backgroundColor: color }}
                />
              </div>

              <p className="line-clamp-3 min-h-[3em] text-[0.875rem] leading-relaxed text-[var(--paper-dim)]">
                {p.description || "Без описания"}
              </p>

              <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-[var(--line-soft)] pt-4">
                <Link
                  to={`/projects/${p.id}/folder`}
                  className="mono inline-flex min-h-11 items-center rounded-none border border-[var(--line)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--paper-dim)] transition-colors hover:border-[var(--mute)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
                >
                  Открыть папку
                </Link>
                <Button variant="secondary" size="sm" onClick={() => onEdit(p)}>
                  Правка
                </Button>
                <Button variant="danger" size="sm" onClick={() => onDelete(p)}>
                  Удалить
                </Button>
              </div>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
