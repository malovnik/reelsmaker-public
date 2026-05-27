import { useEffect, useState } from "react";
import { projectsApi, type Project } from "@/lib/api/projects";
import { Button, Field, Input, Modal, Textarea } from "@/components/ui";
import { useToast } from "@/contexts";

interface Props {
  open: boolean;
  project: Project | null;
  onClose: () => void;
  onSaved: () => void;
}

const DEFAULT_COLOR = "#C9A84C";
const MAX_NAME_LENGTH = 256;

/**
 * Создание/правка проекта в VD-04-модалке (max-h, sticky header/footer,
 * фокус-трап через ui/Modal). Ошибки — humanizeError через useToast.
 */
export function ProjectFormModal({ open, project, onClose, onSaved }: Props) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [saving, setSaving] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (project) {
      setName(project.name);
      setDescription(project.description);
      setColor(project.color && project.color.trim() ? project.color : DEFAULT_COLOR);
    } else {
      setName("");
      setDescription("");
      setColor(DEFAULT_COLOR);
    }
    setNameError(null);
    setSaving(false);
  }, [open, project]);

  const isEdit = project !== null;

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError("Дайте проекту название — без него не сохранить.");
      return;
    }
    setNameError(null);
    setSaving(true);
    try {
      if (project) {
        await projectsApi.updateProject(project.id, { name: trimmed, description, color });
        toast.success("Проект обновлён");
      } else {
        await projectsApi.createProject({ name: trimmed, description, color });
        toast.success("Проект создан");
      }
      onSaved();
    } catch (err) {
      toast.showError(err);
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title={isEdit ? "Правка проекта" : "Новый проект"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Отмена
          </Button>
          <Button variant="primary" onClick={handleSave} loading={saving}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Input
          label="Название"
          required
          value={name}
          maxLength={MAX_NAME_LENGTH}
          placeholder="Канал про ИИ"
          error={nameError ?? undefined}
          onChange={(e) => setName(e.target.value)}
        />

        <Textarea
          label="Описание"
          hint="Необязательно — короткая пометка, о чём проект."
          rows={3}
          value={description}
          placeholder="Нарезки для клиентского блога"
          onChange={(e) => setDescription(e.target.value)}
        />

        <Field label="Цвет метки">
          {({ id }) => (
            <div className="flex items-center gap-3">
              <input
                id={id}
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="size-11 cursor-pointer rounded-none border border-[var(--line)] bg-transparent"
              />
              <span className="mono text-[0.8125rem] uppercase tracking-[0.1em] text-[var(--paper-dim)]">
                {color}
              </span>
            </div>
          )}
        </Field>
      </div>
    </Modal>
  );
}
