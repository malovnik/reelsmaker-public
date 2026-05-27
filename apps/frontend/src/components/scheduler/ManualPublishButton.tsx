
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  schedulerApi,
  type AccountProfile,
  type PublerAccount,
} from "@/lib/api/scheduler";

interface Props {
  artifactId: number;
  jobId: string;
  accounts?: PublerAccount[];
  profiles?: AccountProfile[];
  label?: string;
}

function padTwo(n: number): string {
  return String(n).padStart(2, "0");
}

function defaultSchedule(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() + 15);
  return `${d.getFullYear()}-${padTwo(d.getMonth() + 1)}-${padTwo(d.getDate())}T${padTwo(d.getHours())}:${padTwo(d.getMinutes())}`;
}

function toIsoUtc(local: string): string {
  const d = new Date(local);
  return d.toISOString();
}

export function ManualPublishButton({
  artifactId,
  jobId,
  accounts: initialAccounts,
  profiles: initialProfiles,
  label = "Опубликовать",
}: Props) {
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<PublerAccount[]>(
    initialAccounts ?? [],
  );
  const [profiles, setProfiles] = useState<AccountProfile[]>(
    initialProfiles ?? [],
  );
  const [loaded, setLoaded] = useState<boolean>(
    Boolean(initialAccounts && initialProfiles),
  );
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [accountId, setAccountId] = useState<string>("");
  const [scheduledLocal, setScheduledLocal] = useState<string>(
    defaultSchedule(),
  );
  const [customCaption, setCustomCaption] = useState<string>("");
  const [customTitle, setCustomTitle] = useState<string>("");

  const profileMap = useMemo(() => {
    const m = new Map<string, AccountProfile>();
    for (const p of profiles) m.set(p.publer_account_id, p);
    return m;
  }, [profiles]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, p] = await Promise.all([
        schedulerApi.listPublerAccounts(),
        schedulerApi.listProfiles(),
      ]);
      setAccounts(a);
      setProfiles(p);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!open || loaded) return;
    void loadData();
  }, [open, loaded, loadData]);

  const eligibleAccounts = useMemo(
    () => accounts.filter((a) => profileMap.has(a.id)),
    [accounts, profileMap],
  );

  const handleSubmit = useCallback(async () => {
    if (!accountId) {
      setError("Выбери аккаунт");
      return;
    }
    if (!scheduledLocal) {
      setError("Укажи дату и время");
      return;
    }
    const parsed = new Date(scheduledLocal);
    if (Number.isNaN(parsed.getTime()) || parsed.getTime() <= Date.now()) {
      setError("Время публикации должно быть в будущем.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await schedulerApi.manualPublishOne({
        reel_artifact_id: artifactId,
        job_id: jobId,
        publer_account_id: accountId,
        scheduled_at_utc: toIsoUtc(scheduledLocal),
        custom_caption: customCaption.trim() || null,
        custom_title: customTitle.trim() || null,
      });
      setSuccess("Задача поставлена в очередь");
      setTimeout(() => {
        setOpen(false);
        setSuccess(null);
      }, 1200);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  }, [accountId, scheduledLocal, artifactId, jobId, customCaption, customTitle]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-primary"
      >
        {label}
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => !submitting && setOpen(false)}
        >
          <div
            className="surface-card flex w-full max-w-md flex-col gap-4 p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between gap-3">
              <h3 className="display-serif text-xl text-[color:var(--paper)]">
                Опубликовать рилс #{artifactId}
              </h3>
              <button
                type="button"
                onClick={() => !submitting && setOpen(false)}
                disabled={submitting}
                aria-label="Закрыть"
                className="text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed"
              >
                ×
              </button>
            </header>

            {loading ? (
              <div className="text-sm text-[color:var(--text-secondary)]">
                Загружаю аккаунты…
              </div>
            ) : eligibleAccounts.length === 0 ? (
              <div className="text-sm text-[color:var(--danger)]">
                Нет аккаунтов с настроенным профилем. Открой «Профили
                аккаунтов» и заполни хотя бы один.
              </div>
            ) : (
              <>
                <label className="flex flex-col gap-1.5">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    Аккаунт
                  </span>
                  <select
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
                  >
                    <option value="">— выбери —</option>
                    {eligibleAccounts.map((a) => {
                      const p = profileMap.get(a.id);
                      const name = p?.display_name ?? a.name ?? a.id;
                      const net = p?.network ?? a.provider ?? "—";
                      return (
                        <option key={a.id} value={a.id}>
                          {name} · {net}
                        </option>
                      );
                    })}
                  </select>
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    Дата и время (локальное → UTC)
                  </span>
                  <input
                    type="datetime-local"
                    value={scheduledLocal}
                    onChange={(e) => setScheduledLocal(e.target.value)}
                    className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
                  />
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    Caption (опционально — перезапишет генерацию)
                  </span>
                  <textarea
                    value={customCaption}
                    onChange={(e) => setCustomCaption(e.target.value)}
                    rows={3}
                    placeholder="Оставь пустым — сгенерируется по профилю"
                    className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
                  />
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    Заголовок (для YouTube Shorts)
                  </span>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="Опционально"
                    className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
                  />
                </label>
              </>
            )}

            {error ? (
              <p className="text-[12px] text-[color:var(--danger)]">{error}</p>
            ) : null}
            {success ? (
              <p className="text-[12px] text-[color:var(--gold)]">{success}</p>
            ) : null}

            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={submitting}
                className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={
                  submitting ||
                  loading ||
                  eligibleAccounts.length === 0 ||
                  !accountId
                }
                className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Отправляю…" : "Опубликовать"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
