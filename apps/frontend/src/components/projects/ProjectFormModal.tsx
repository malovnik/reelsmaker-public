
import { useEffect, useState } from "react";
import { projectsApi, type Project } from "@/lib/api/projects";

interface Props {
  open: boolean;
  project: Project | null;
  onClose: () => void;
  onSaved: () => void;
}

const DEFAULT_COLOR = "#6366f1";
const MAX_NAME_LENGTH = 256;

export function ProjectFormModal({ open, project, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (project) {
      setName(project.name);
      setDescription(project.description);
      setColor(
        project.color && project.color.trim() ? project.color : DEFAULT_COLOR,
      );
    } else {
      setName("");
      setDescription("");
      setColor(DEFAULT_COLOR);
    }
    setError(null);
    setSaving(false);
  }, [open, project]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const canSave = name.trim().length > 0 && !saving;

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Название не может быть пустым");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      if (project) {
        await projectsApi.updateProject(project.id, {
          name: trimmed,
          description,
          color,
        });
      } else {
        await projectsApi.createProject({
          name: trimmed,
          description,
          color,
        });
      }
      onSaved();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      setSaving(false);
    }
  };

  const titleId = "project-form-dialog-title";
  const isEdit = project !== null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="surface-card w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2
            id={titleId}
            className="display-serif text-[22px] leading-tight text-[color:var(--paper)]"
          >
            {isEdit ? "Редактировать проект" : "Новый проект"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)]"
          >
            ×
          </button>
        </div>

        <div className="divider my-4">параметры</div>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Название
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={MAX_NAME_LENGTH}
              placeholder="Например: Канал про ИИ"
              required
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Описание
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Короткое описание, опционально"
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Цвет карточки
            </span>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-9 w-16 cursor-pointer rounded-md border border-[color:var(--line)] bg-transparent"
              />
              <span className="mono text-[12px] uppercase tracking-[0.1em] text-[color:var(--paper-dim)]">
                {color}
              </span>
            </div>
          </label>
        </div>

        {error ? (
          <p className="mt-3 text-[11px] text-[color:var(--danger)]">{error}</p>
        ) : null}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}
