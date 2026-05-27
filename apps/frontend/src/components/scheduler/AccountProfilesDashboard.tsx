
import { useCallback, useMemo, useState } from "react";
import {
  schedulerApi,
  type AccountProfile,
  type PublerAccount,
  type PublerNetwork,
} from "@/lib/api/scheduler";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";
import { humanizeError } from "@/lib/humanizeError";

interface Props {
  initialAccounts: PublerAccount[];
  initialProfiles: AccountProfile[];
  initialError: string | null;
}

interface FormState {
  language: string;
  audience: string;
  tone: string;
  default_hashtags: string[];
  banned_words: string[];
  cta_style: string;
  max_caption_length: number;
}

const LANGUAGES: Array<{ code: string; label: string }> = [
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
  { code: "vi", label: "Tiếng Việt" },
  { code: "zh", label: "中文" },
];

const EMPTY_FORM: FormState = {
  language: "ru",
  audience: "",
  tone: "",
  default_hashtags: [],
  banned_words: [],
  cta_style: "",
  max_caption_length: 2200,
};

function inferNetwork(account: PublerAccount): PublerNetwork {
  const s = (account.provider || account.type || "").toLowerCase();
  if (s.includes("youtube") || s.includes("yt")) return "youtube";
  return "instagram";
}

function profileToForm(p: AccountProfile): FormState {
  return {
    language: p.language || "ru",
    audience: p.audience || "",
    tone: p.tone || "",
    default_hashtags: Array.isArray(p.default_hashtags) ? p.default_hashtags : [],
    banned_words: Array.isArray(p.banned_words) ? p.banned_words : [],
    cta_style: p.cta_style || "",
    max_caption_length: p.max_caption_length ?? 2200,
  };
}

// ────────────────────────── TagInput ──────────────────────────

function TagInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = useCallback(
    (raw: string) => {
      const parts = raw
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (parts.length === 0) return;
      const merged = [...value];
      for (const p of parts) {
        if (!merged.includes(p)) merged.push(p);
      }
      onChange(merged);
      setDraft("");
    },
    [value, onChange],
  );

  const remove = useCallback(
    (idx: number) => {
      const next = value.slice();
      next.splice(idx, 1);
      onChange(next);
    },
    [value, onChange],
  );

  return (
    <label className="flex flex-col gap-1.5">
      <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-2 py-1.5 focus-within:border-[color:var(--gold)]">
        {value.map((tag, idx) => (
          <span
            key={`${tag}-${idx}`}
            className="mono flex items-center gap-1 rounded border border-[color:var(--line)] bg-[color:var(--ink)] px-2 py-0.5 text-[11px] text-[color:var(--paper)]"
          >
            {tag}
            <button
              type="button"
              onClick={() => remove(idx)}
              aria-label={`Удалить ${tag}`}
              className="text-[color:var(--mute-2)] transition-colors hover:text-[color:var(--danger)]"
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit(draft);
            } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
              e.preventDefault();
              remove(value.length - 1);
            }
          }}
          onBlur={() => {
            if (draft.trim()) commit(draft);
          }}
          placeholder={value.length === 0 ? placeholder : ""}
          className="min-w-[120px] flex-1 bg-transparent text-[13px] text-[color:var(--paper)] outline-none placeholder:text-[color:var(--mute-2)]"
        />
      </div>
    </label>
  );
}

// ────────────────────────── AccountCard ──────────────────────────

interface AccountCardProps {
  account: PublerAccount;
  profile: AccountProfile | null;
  onSaved: (saved: AccountProfile) => void;
  onDeleted: () => void;
}

function AccountCard({ account, profile, onSaved, onDeleted }: AccountCardProps) {
  const toast = useToast();
  const confirm = useConfirm();
  const displayName = account.name || account.id;
  const network: PublerNetwork = profile?.network ?? inferNetwork(account);

  const [form, setForm] = useState<FormState>(
    profile ? profileToForm(profile) : EMPTY_FORM,
  );
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(profile === null);

  const handleSave = useCallback(async () => {
    if (form.max_caption_length < 1) {
      setLocalError("Длина должна быть больше 0");
      return;
    }
    setSaving(true);
    setLocalError(null);
    try {
      const saved = await schedulerApi.upsertProfile(account.id, {
        display_name: displayName,
        network,
        language: form.language,
        audience: form.audience,
        tone: form.tone,
        default_hashtags: form.default_hashtags,
        banned_words: form.banned_words,
        cta_style: form.cta_style,
        max_caption_length: form.max_caption_length,
      });
      onSaved(saved);
    } catch (exc) {
      toast.showError(exc);
    } finally {
      setSaving(false);
    }
  }, [account.id, displayName, network, form, onSaved, toast]);

  const handleDelete = useCallback(async () => {
    if (!profile) return;
    const ok = await confirm({
      title: `Удалить профиль «${displayName}»?`,
      description: "Для аккаунта снова вернутся значения по умолчанию.",
      confirmLabel: "Удалить",
      destructive: true,
    });
    if (!ok) return;
    setDeleting(true);
    setLocalError(null);
    try {
      await schedulerApi.deleteProfile(account.id);
      setForm(EMPTY_FORM);
      onDeleted();
    } catch (exc) {
      toast.showError(exc);
    } finally {
      setDeleting(false);
    }
  }, [account.id, displayName, profile, onDeleted, confirm, toast]);

  const hasProfile = profile !== null;

  return (
    <section className="surface-card flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="display-serif truncate text-xl text-[color:var(--paper)]">
            {displayName}
          </div>
          <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            {network} · id · {account.id}
            {account.status ? ` · ${account.status}` : ""}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="mono border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
            style={{
              color: hasProfile ? "var(--gold)" : "var(--mute-2)",
              borderColor: hasProfile ? "var(--gold)" : "var(--mute-2)",
            }}
          >
            {hasProfile ? "профиль задан" : "без профиля"}
          </span>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
          >
            {expanded ? "Свернуть" : "Настроить"}
          </button>
        </div>
      </div>

      {expanded ? (
        <div className="flex flex-col gap-4 pt-2">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Язык постов
              </span>
              <select
                value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
                className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                Сеть
              </span>
              <input
                type="text"
                value={network}
                readOnly
                className="rounded-md border border-[color:var(--line)] bg-[color:var(--ink)] px-3 py-2 text-[13px] text-[color:var(--paper-dim)] outline-none"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Аудитория
            </span>
            <textarea
              value={form.audience}
              onChange={(e) => setForm({ ...form, audience: e.target.value })}
              rows={2}
              placeholder="Кто подписан, что их волнует"
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Тон голоса
            </span>
            <textarea
              value={form.tone}
              onChange={(e) => setForm({ ...form, tone: e.target.value })}
              rows={2}
              placeholder="Серьёзный, ироничный, экспертный…"
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <TagInput
            label="Базовые хэштеги"
            value={form.default_hashtags}
            onChange={(next) => setForm({ ...form, default_hashtags: next })}
            placeholder="#reels #видеомонтаж"
          />

          <TagInput
            label="Стоп-слова"
            value={form.banned_words}
            onChange={(next) => setForm({ ...form, banned_words: next })}
            placeholder="через Enter или запятую"
          />

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Стиль CTA
            </span>
            <textarea
              value={form.cta_style}
              onChange={(e) => setForm({ ...form, cta_style: e.target.value })}
              rows={2}
              placeholder="Как подписываем призыв к действию"
              className="resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors placeholder:text-[color:var(--mute-2)] focus:border-[color:var(--gold)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              Макс. длина caption
            </span>
            <input
              type="number"
              min={1}
              value={form.max_caption_length}
              onChange={(e) =>
                setForm({
                  ...form,
                  max_caption_length: Number(e.target.value) || 1,
                })
              }
              className="w-36 rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
            />
          </label>

          {localError ? (
            <p className="text-[11px] text-[color:var(--danger)]">{localError}</p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
            {hasProfile ? (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting || saving}
                className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? "Удаляю…" : "Удалить профиль"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || deleting}
              className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Сохраняю…" : "Сохранить"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

// ────────────────────────── Dashboard ──────────────────────────

export function AccountProfilesDashboard({
  initialAccounts,
  initialProfiles,
  initialError,
}: Props) {
  const [accounts, setAccounts] = useState<PublerAccount[]>(initialAccounts);
  const [profiles, setProfiles] = useState<AccountProfile[]>(initialProfiles);
  const [error, setError] = useState<string | null>(initialError);
  const [refreshing, setRefreshing] = useState(false);

  const profileMap = useMemo(() => {
    const m = new Map<string, AccountProfile>();
    for (const p of profiles) m.set(p.publer_account_id, p);
    return m;
  }, [profiles]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [a, p] = await Promise.all([
        schedulerApi.listPublerAccounts(),
        schedulerApi.listProfiles(),
      ]);
      setAccounts(a);
      setProfiles(p);
    } catch (exc) {
      const human = humanizeError(exc);
      setError(`${human.title}. ${human.detail}`);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const handleSaved = useCallback((saved: AccountProfile) => {
    setProfiles((prev) => {
      const next = prev.filter(
        (p) => p.publer_account_id !== saved.publer_account_id,
      );
      next.push(saved);
      return next;
    });
  }, []);

  const handleDeleted = useCallback((accountId: string) => {
    setProfiles((prev) =>
      prev.filter((p) => p.publer_account_id !== accountId),
    );
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          всего аккаунтов · {accounts.length} · профилей · {profiles.length}
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={refreshing}
          className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshing ? "Обновляю…" : "Обновить список"}
        </button>
      </div>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      {accounts.length === 0 ? (
        <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
          <div className="display-serif text-2xl text-[color:var(--paper)]">
            Аккаунтов пока нет
          </div>
          <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
            Подключи Instagram или YouTube в кабинете Publer — после этого
            аккаунты подтянутся сюда и можно будет настроить под них профиль.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {accounts.map((acc) => (
            <AccountCard
              key={acc.id}
              account={acc}
              profile={profileMap.get(acc.id) ?? null}
              onSaved={handleSaved}
              onDeleted={() => handleDeleted(acc.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
