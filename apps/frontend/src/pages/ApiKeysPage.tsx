import { useCallback, useEffect, useState } from "react";

import { api, type ApiKeysStatus, type ApiKeysUpdate } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useToast } from "@/contexts";

/**
 * /settings/api-keys — ввод ключей API из интерфейса, без правки .env.
 *
 * Значения наружу не отдаются: бэк возвращает только статус «задан/не задан».
 * Ввод нового значения перезаписывает ключ; «Очистить» убирает runtime-ключ
 * (возврат к .env, если он там есть). Применяется без перезапуска сервера.
 */

interface KeyField {
  name: keyof ApiKeysStatus;
  label: string;
  hint: string;
  placeholder: string;
}

const FIELDS: KeyField[] = [
  {
    name: "gemini_api_key",
    label: "Gemini API key",
    hint: "Обязателен — ядро нарезки. Бесплатный ключ: aistudio.google.com/apikey",
    placeholder: "AIza…",
  },
  {
    name: "deepgram_api_key",
    label: "Deepgram API key",
    hint: "Нужен для распознавания речи на Windows/Linux (и Intel-Mac). deepgram.com",
    placeholder: "ключ Deepgram",
  },
  {
    name: "publer_api_key",
    label: "Publer API key",
    hint: "Для публикации рилсов в соцсети. app.publer.com → Settings → API.",
    placeholder: "ключ Publer",
  },
  {
    name: "publer_workspace_id",
    label: "Publer Workspace ID",
    hint: "ID рабочего пространства Publer (идёт в паре с ключом Publer).",
    placeholder: "workspace id",
  },
];

export default function ApiKeysPage() {
  const toast = useToast();
  const [status, setStatus] = useState<ApiKeysStatus | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.getApiKeys());
    } catch (err) {
      toast.showError(err);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = useCallback(
    async (payload: ApiKeysUpdate, okMessage: string) => {
      setSaving(true);
      setFlash(null);
      try {
        const next = await api.updateApiKeys(payload);
        setStatus(next);
        setDrafts({});
        setFlash(okMessage);
      } catch (err) {
        toast.showError(err);
      } finally {
        setSaving(false);
      }
    },
    [toast],
  );

  const handleSave = useCallback(() => {
    // Отправляем только реально введённые поля (PATCH-семантика).
    const payload: ApiKeysUpdate = {};
    for (const field of FIELDS) {
      const value = drafts[field.name]?.trim();
      if (value) payload[field.name] = value;
    }
    if (Object.keys(payload).length === 0) {
      setFlash("Нечего сохранять — введите хотя бы один ключ.");
      return;
    }
    void apply(payload, "Ключи сохранены и применены.");
  }, [drafts, apply]);

  const handleClear = useCallback(
    (name: keyof ApiKeysStatus) => {
      void apply({ [name]: "" }, "Ключ очищен (используется значение из .env, если задано).");
    },
    [apply],
  );

  return (
    <div className="flex flex-col gap-8 pb-24">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">Ключи API</h1>
        <p className="page-subtitle">
          Введите ключи прямо здесь — править файл .env не нужно. Значения
          хранятся локально, наружу не показываются и применяются сразу.
        </p>
      </header>

      <div className="flex max-w-2xl flex-col gap-6">
        {FIELDS.map((field) => {
          const isSet = status?.[field.name] ?? false;
          return (
            <div key={field.name} className="flex flex-col gap-2">
              <Input
                type="password"
                autoComplete="off"
                label={field.label}
                hint={field.hint}
                placeholder={field.placeholder}
                value={drafts[field.name] ?? ""}
                onChange={(e) =>
                  setDrafts((prev) => ({ ...prev, [field.name]: e.target.value }))
                }
              />
              <div className="flex items-center gap-3 text-[0.8125rem]">
                <span
                  className={
                    isSet
                      ? "text-[color:var(--ok,#6ea36e)]"
                      : "text-[color:var(--mute)]"
                  }
                >
                  {isSet ? "● задан" : "○ не задан"}
                </span>
                {isSet && (
                  <button
                    type="button"
                    onClick={() => handleClear(field.name)}
                    disabled={saving}
                    className="font-mono text-[0.75rem] uppercase tracking-[0.1em] text-[color:var(--mute-2)] underline-offset-4 hover:text-[color:var(--paper)] hover:underline disabled:opacity-50"
                  >
                    очистить
                  </button>
                )}
              </div>
            </div>
          );
        })}

        <div className="flex items-center gap-4">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Сохраняю…" : "Сохранить"}
          </Button>
          {flash && (
            <span className="text-[0.8125rem] text-[color:var(--mute)]">{flash}</span>
          )}
        </div>
      </div>
    </div>
  );
}
