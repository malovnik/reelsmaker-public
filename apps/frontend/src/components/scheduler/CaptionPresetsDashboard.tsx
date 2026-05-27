
import { useCallback, useMemo, useState } from "react";
import {
  schedulerApi,
  type AccountProfile,
  type CaptionPreset,
} from "@/lib/api/scheduler";
import { CaptionPresetFormModal } from "./CaptionPresetFormModal";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";
import { humanizeError } from "@/lib/humanizeError";

interface Props {
  initialPresets: CaptionPreset[];
  profiles: AccountProfile[];
  initialError: string | null;
}

const GLOBAL_KEY = "__global__";
const GLOBAL_LABEL = "Глобальные пресеты";

function groupPresets(
  presets: CaptionPreset[],
  profiles: AccountProfile[],
): Array<{ key: string; label: string; sub: string | null; items: CaptionPreset[] }> {
  const profileByAccount = new Map<string, AccountProfile>();
  for (const p of profiles) profileByAccount.set(p.publer_account_id, p);

  const groups = new Map<
    string,
    { key: string; label: string; sub: string | null; items: CaptionPreset[] }
  >();

  groups.set(GLOBAL_KEY, {
    key: GLOBAL_KEY,
    label: GLOBAL_LABEL,
    sub: "применяются ко всем аккаунтам",
    items: [],
  });

  for (const preset of presets) {
    const key = preset.account_id ?? GLOBAL_KEY;
    if (!groups.has(key)) {
      const profile = preset.account_id
        ? profileByAccount.get(preset.account_id)
        : undefined;
      groups.set(key, {
        key,
        label: profile?.display_name ?? preset.account_id ?? GLOBAL_LABEL,
        sub: profile?.network ?? (preset.account_id ? `id · ${preset.account_id}` : null),
        items: [],
      });
    }
    groups.get(key)!.items.push(preset);
  }

  return Array.from(groups.values()).sort((a, b) => {
    if (a.key === GLOBAL_KEY) return -1;
    if (b.key === GLOBAL_KEY) return 1;
    return a.label.localeCompare(b.label, "ru");
  });
}

export function CaptionPresetsDashboard({
  initialPresets,
  profiles,
  initialError,
}: Props) {
  const toast = useToast();
  const confirm = useConfirm();
  const [presets, setPresets] = useState<CaptionPreset[]>(initialPresets);
  const [error, setError] = useState<string | null>(initialError);
  const [editing, setEditing] = useState<CaptionPreset | null>(null);
  const [creating, setCreating] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const groups = useMemo(
    () => groupPresets(presets, profiles),
    [presets, profiles],
  );

  const refresh = useCallback(async () => {
    try {
      const fresh = await schedulerApi.listPresets();
      setPresets(fresh);
      setError(null);
    } catch (exc) {
      const human = humanizeError(exc);
      setError(`${human.title}. ${human.detail}`);
    }
  }, []);

  const handleToggle = useCallback(async (preset: CaptionPreset) => {
    setTogglingId(preset.id);
    try {
      const updated = await schedulerApi.updatePreset(preset.id, {
        is_active: !preset.is_active,
      });
      setPresets((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    } catch (exc) {
      toast.showError(exc);
    } finally {
      setTogglingId(null);
    }
  }, [toast]);

  const handleDelete = useCallback(async (preset: CaptionPreset) => {
    const ok = await confirm({
      title: `Удалить пресет «${preset.name}»?`,
      description: "Шаблон подписи пропадёт из списка без возможности вернуть.",
      confirmLabel: "Удалить",
      destructive: true,
    });
    if (!ok) return;
    setDeletingId(preset.id);
    try {
      await schedulerApi.deletePreset(preset.id);
      setPresets((prev) => prev.filter((p) => p.id !== preset.id));
    } catch (exc) {
      toast.showError(exc);
    } finally {
      setDeletingId(null);
    }
  }, [confirm, toast]);

  const modalOpen = creating || editing !== null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          всего пресетов · {presets.length}
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="btn btn-primary"
        >
          + Новый пресет
        </button>
      </div>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      {presets.length === 0 ? (
        <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
          <div className="display-serif text-2xl text-[color:var(--paper)]">
            Пока ни одного пресета
          </div>
          <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
            Создай шаблоны подписей — они автоматически добавятся в начало или
            конец сгенерированных caption для каждого рилса.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {groups.map((group) => (
            <section key={group.key} className="flex flex-col gap-3">
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <div className="display-serif truncate text-lg text-[color:var(--paper)]">
                    {group.label}
                  </div>
                  {group.sub ? (
                    <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                      {group.sub}
                    </div>
                  ) : null}
                </div>
                <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  {group.items.length} шт
                </div>
              </div>

              {group.items.length === 0 ? (
                <div className="surface-card p-4 text-sm text-[color:var(--text-secondary)]">
                  Пресетов нет. Создай первый — пригодится для одинаковых
                  подписей под Shorts и Reels.
                </div>
              ) : (
                <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {group.items.map((preset) => (
                    <li key={preset.id} className="surface-card flex flex-col gap-3 p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 flex-col gap-1">
                          <div className="display-serif truncate text-lg text-[color:var(--paper)]">
                            {preset.name}
                          </div>
                          <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                            id · {preset.id} · {preset.position === "prepend" ? "начало" : "конец"}
                          </div>
                        </div>
                        <span
                          className="mono shrink-0 border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                          style={{
                            color:
                              preset.position === "prepend"
                                ? "var(--gold)"
                                : "var(--paper-dim)",
                            borderColor:
                              preset.position === "prepend"
                                ? "var(--gold)"
                                : "var(--line)",
                          }}
                        >
                          {preset.position === "prepend" ? "PRE" : "APP"}
                        </span>
                      </div>

                      <pre className="line-clamp-3 whitespace-pre-wrap rounded-md border border-[color:var(--line)] bg-[color:var(--ink)] p-3 text-[12px] leading-relaxed text-[color:var(--paper-dim)]">
                        {preset.content}
                      </pre>

                      <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
                        <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-[color:var(--paper-dim)]">
                          <input
                            type="checkbox"
                            checked={preset.is_active}
                            onChange={() => handleToggle(preset)}
                            disabled={togglingId === preset.id}
                            className="accent-[color:var(--gold)]"
                          />
                          {preset.is_active ? "активен" : "выключен"}
                        </label>
                        <button
                          type="button"
                          onClick={() => setEditing(preset)}
                          className="ml-auto rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
                        >
                          Редактировать
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(preset)}
                          disabled={deletingId === preset.id}
                          className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {deletingId === preset.id ? "Удаляю…" : "Удалить"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}

      <CaptionPresetFormModal
        open={modalOpen}
        preset={editing}
        profiles={profiles}
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
