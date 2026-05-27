import { useEffect, useState } from "react";
import {
  schedulerApi,
  type ScheduleAssignment,
} from "@/lib/api/scheduler";
import { Button, Field, Input, Modal, Textarea } from "@/components/ui";
import { useToast } from "@/contexts";
import {
  DISPLAY_TZ,
  localInputToUtcIso,
  utcIsoToLocalInput,
} from "./campaignTime";
import { networkLabel } from "./statusMeta";

interface Props {
  open: boolean;
  assignment: ScheduleAssignment | null;
  onClose: () => void;
  onSaved: (updated: ScheduleAssignment) => void;
}

const tzCity = DISPLAY_TZ.split("/")[1]?.replace("_", " ") ?? DISPLAY_TZ;

/**
 * Модалка правки публикации: подпись, заголовок (для Shorts), хэштеги, время.
 * VD-04: max-h, sticky header/footer, фокус-трап (через ui/Modal). Ошибки —
 * humanizeError через useToast.
 */
export function AssignmentEditModal({ open, assignment, onClose, onSaved }: Props) {
  const toast = useToast();
  const [caption, setCaption] = useState("");
  const [title, setTitle] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");
  const [scheduledLocal, setScheduledLocal] = useState("");
  const [saving, setSaving] = useState(false);
  const [timeError, setTimeError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !assignment) return;
    setCaption(assignment.caption ?? "");
    setTitle(assignment.title ?? "");
    setHashtagsText((assignment.hashtags ?? []).join(" "));
    setScheduledLocal(utcIsoToLocalInput(assignment.scheduled_at_utc));
    setTimeError(null);
    setSaving(false);
  }, [open, assignment]);

  if (!assignment) return null;

  const isYoutube = assignment.network === "youtube";

  const handleSave = async () => {
    setTimeError(null);
    const hashtags = hashtagsText
      .split(/[\s,]+/)
      .map((t) => t.replace(/^#+/, "").trim())
      .filter((t) => t.length > 0);
    let scheduledUtc: string | undefined;
    if (scheduledLocal) {
      const parsed = localInputToUtcIso(scheduledLocal);
      if (!parsed) {
        setTimeError("Проверьте дату и время — формат не распознан.");
        return;
      }
      scheduledUtc = parsed;
    }
    setSaving(true);
    try {
      const updated = await schedulerApi.updateAssignment(assignment.id, {
        caption,
        title: isYoutube ? title : undefined,
        hashtags,
        scheduled_at_utc: scheduledUtc,
      });
      toast.success("Публикация сохранена");
      onSaved(updated);
    } catch (err) {
      toast.showError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Правка публикации"
      subtitle={`${networkLabel(assignment.network)} · аккаунт ${assignment.publer_account_id}`}
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
        {isYoutube ? (
          <Input
            label="Заголовок для Shorts"
            hint="До 100 символов — показывается над видео в YouTube."
            value={title}
            maxLength={100}
            placeholder="Хук за 3 секунды"
            onChange={(e) => setTitle(e.target.value)}
          />
        ) : null}

        <Textarea
          label="Подпись"
          rows={6}
          value={caption}
          placeholder="Первая строка цепляет, дальше — раскрытие."
          onChange={(e) => setCaption(e.target.value)}
        />

        <Input
          label="Хэштеги"
          hint="Через пробел или запятую, решётка не нужна."
          value={hashtagsText}
          placeholder="нарезка деньги хук"
          onChange={(e) => setHashtagsText(e.target.value)}
        />

        <Field label={`Время публикации (${tzCity})`} error={timeError ?? undefined}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="datetime-local"
              value={scheduledLocal}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              onChange={(e) => setScheduledLocal(e.target.value)}
              className="w-full rounded-none border border-[var(--line)] bg-[var(--ink)] px-[18px] py-[14px] text-[0.9375rem] leading-snug text-[var(--paper)] transition-colors duration-200 hover:border-[var(--mute)] focus:border-[var(--gold)] focus:outline-none aria-[invalid=true]:border-[var(--danger)]"
            />
          )}
        </Field>
      </div>
    </Modal>
  );
}
