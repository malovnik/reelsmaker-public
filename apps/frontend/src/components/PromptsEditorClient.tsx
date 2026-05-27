
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type PromptPayload } from "@/lib/api";
import { useToast } from "@/contexts/ToastContext";

const PROMPT_DESCRIPTIONS: Record<string, string> = {
  pass1_explicit:
    "Первый проход — явные моменты: готовые к вырезке тезисы и законченные мысли.",
  pass2_implicit:
    "Второй проход — скрытые моменты: эмоциональные пики, неожиданные откровения, противоречия.",
  pass3_virtual_cut:
    "Третий проход — собирает рилсы из кусков, взятых из разных мест видео.",
  pass1_reduce:
    "Свёртка первого прохода: объединяет дубликаты из разных частей длинного видео.",
  pass2_reduce:
    "Свёртка второго прохода: объединяет похожие эмоциональные моменты из разных частей.",
};

interface Props {
  initial: PromptPayload[];
}

export function PromptsEditorClient({ initial }: Props) {
  const toast = useToast();
  const [prompts, setPrompts] = useState<PromptPayload[]>(initial);
  const [selectedKey, setSelectedKey] = useState<string>(initial[0]?.key ?? "");
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<{
    kind: "ok" | "error";
    message: string;
  } | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (flashTimerRef.current !== null) {
        clearTimeout(flashTimerRef.current);
      }
    };
  }, []);

  const selected = useMemo(
    () => prompts.find((p) => p.key === selectedKey),
    [prompts, selectedKey],
  );

  const onChange = (content: string) => {
    if (!selected) return;
    setPrompts((prev) =>
      prev.map((p) => (p.key === selected.key ? { ...p, content } : p)),
    );
  };

  const onSave = async () => {
    if (!selected) return;
    setSaving(true);
    setFlash(null);
    try {
      const updated = await api.upsertPrompt(selected.key, selected.content);
      setPrompts((prev) =>
        prev.map((p) => (p.key === updated.key ? updated : p)),
      );
      setFlash({ kind: "ok", message: "Сохранено" });
    } catch (err) {
      toast.showError(err);
    } finally {
      setSaving(false);
      if (flashTimerRef.current !== null) {
        clearTimeout(flashTimerRef.current);
      }
      flashTimerRef.current = setTimeout(() => {
        setFlash(null);
        flashTimerRef.current = null;
      }, 2500);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
      <nav className="flex flex-col gap-1">
        {prompts.map((p) => {
          const active = p.key === selectedKey;
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => setSelectedKey(p.key)}
              className={`rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                active
                  ? "bg-[color:var(--accent-primary-subtle)] text-[color:var(--accent-primary-hover)]"
                  : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-sunken)] hover:text-[color:var(--text-primary)]"
              }`}
            >
              <div className="font-mono text-xs font-medium">{p.key}</div>
              <div
                className={`mt-0.5 text-[11px] ${
                  active
                    ? "text-[color:var(--accent-primary)]"
                    : "text-[color:var(--text-muted)]"
                }`}
              >
                {p.content.length} символов
              </div>
            </button>
          );
        })}
      </nav>

      <div className="flex flex-col gap-4">
        {selected ? (
          <>
            <div>
              <h3 className="font-mono text-sm text-[color:var(--text-primary)]">
                {selected.key}
              </h3>
              {PROMPT_DESCRIPTIONS[selected.key] && (
                <p className="mt-1 text-xs text-[color:var(--text-muted)]">
                  {PROMPT_DESCRIPTIONS[selected.key]}
                </p>
              )}
            </div>
            <textarea
              value={selected.content}
              onChange={(e) => onChange(e.target.value)}
              className="min-h-[420px] w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 font-mono text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
              spellCheck={false}
            />
            <div className="flex items-center gap-3">
              <button
                onClick={onSave}
                disabled={saving}
                className="rounded-lg bg-[color:var(--accent-primary)] px-4 py-2 text-sm font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]"
              >
                {saving ? "Сохраняем…" : "Сохранить"}
              </button>
              {flash && (
                <span
                  className={`text-xs font-medium ${
                    flash.kind === "ok"
                      ? "text-[color:var(--success)]"
                      : "text-[color:var(--danger)]"
                  }`}
                >
                  {flash.message}
                </span>
              )}
            </div>
          </>
        ) : (
          <div className="surface-card border-dashed p-6 text-sm text-[color:var(--text-muted)]">
            Промпты не загрузились. Сервер должен создать их при запуске —
            попробуй перезагрузить страницу.
          </div>
        )}
      </div>
    </div>
  );
}
