
import { useEffect, useId, useState } from "react";
import {
  schedulerApi,
  type AccountProfile,
  type CaptionPreset,
  type CaptionPresetPosition,
} from "@/lib/api/scheduler";

interface Props {
  open: boolean;
  preset: CaptionPreset | null;
  profiles: AccountProfile[];
  onClose: () => void;
  onSaved: () => void;
}

const MAX_NAME_LENGTH = 120;

export function CaptionPresetFormModal({
  open,
  preset,
  profiles,
  onClose,
  onSaved,
}: Props) {
  const [name, setName] = useState("");
  const [position, setPosition] = useState<CaptionPresetPosition>("append");
  const [content, setContent] = useState("");
  const [accountId, setAccountId] = useState<string>("");
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const radioGroupName = useId();

  useEffect(() => {
    if (!open) return;
    if (preset) {
      setName(preset.name);
      setPosition(preset.position);
      setContent(preset.content);
      setAccountId(preset.account_id ?? "");
      setIsActive(preset.is_active);
    } else {
      setName("");
      setPosition("append");
      setContent("");
      setAccountId("");
      setIsActive(true);
    }
    setError(null);
    setSaving(false);
  }, [open, preset]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const canSave =
    name.trim().length > 0 && content.trim().length > 0 && !saving;

  const handleSave = async () => {
    const trimmedName = name.trim();
    const trimmedContent = content.trim();
    if (!trimmedName || !trimmedContent) {
      setError("Заполни название и содержимое");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const scope = accountId === "" ? null : accountId;
      if (preset) {
        await schedulerApi.updatePreset(preset.id, {
          name: trimmedName,
          position,
          content: trimmedContent,
          account_id: scope,
          is_active: isActive,
        });
      } else {
        await schedulerApi.createPreset({
          name: trimmedName,
          position,
          content: trimmedContent,
          account_id: scope,
        });
      }
      onSaved();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSaving(false);
    }
  };

  const titleId = "preset-form-dialog-title";
  const isEdit = preset !== null;

  const previewBody =
    "{сгенерированный caption про рилс}";
  const preview =
    position === "prepend"
      ? `${trimNl(content)}\n\n${previewBody}`
      : `${previewBody}\n\n${trimNl(content)}`;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="surface-card w-full max-w-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2
            id={titleId}
            className="display-serif text-[22px] leading-tight text-[color:var(--paper)]"
          >
            {isEdit ? "Редактировать пресет" : "Новый пресет"}
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
              placeholder="Например: Подпись с CTA"
              required
              className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <fieldset className="flex flex-col gap-1.5">
              <legend className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Позиция
              </legend>
              <div className="flex gap-2">
                <label className="flex flex-1 cursor-pointer items-center gap-2 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] transition-colors has-[:checked]:border-[color:var(--gold)]">
                  <input
                    type="radio"
                    name={radioGroupName}
                    value="prepend"
                    checked={position === "prepend"}
                    onChange={() => setPosition("prepend")}
                    className="accent-[color:var(--gold)]"
                  />
                  В начало
                </label>
                <label className="flex flex-1 cursor-pointer items-center gap-2 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] transition-colors has-[:checked]:border-[color:var(--gold)]">
                  <input
                    type="radio"
                    name={radioGroupName}
                    value="append"
                    checked={position === "append"}
                    onChange={() => setPosition("append")}
                    className="accent-[color:var(--gold)]"
                  />
                  В конец
                </label>
              </div>
            </fieldset>

            <label className="flex flex-col gap-1.5">
              <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Область применения
              </span>
              <select
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
              >
                <option value="">Глобальный (все аккаунты)</option>
                {profiles.map((p) => (
                  <option key={p.publer_account_id} value={p.publer_account_id}>
                    {p.display_name} · {p.network}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Содержимое
            </span>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              placeholder="Текст, который будет добавлен в caption"
              required
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          {isEdit ? (
            <label className="flex cursor-pointer items-center gap-2 text-[13px] text-[color:var(--paper)]">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="accent-[color:var(--gold)]"
              />
              Активен
            </label>
          ) : null}

          <div className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Превью
            </span>
            <pre className="whitespace-pre-wrap rounded-md border border-[color:var(--line)] bg-[color:var(--ink)] p-3 text-[12px] leading-relaxed text-[color:var(--paper-dim)]">
              {content.trim() ? preview : previewBody}
            </pre>
          </div>
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

function trimNl(s: string): string {
  return s.replace(/^\n+|\n+$/g, "");
}
