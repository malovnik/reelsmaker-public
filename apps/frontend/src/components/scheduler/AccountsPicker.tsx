
import { Link } from "react-router-dom";
import { useMemo } from "react";
import type { AccountProfile, PublerAccount } from "@/lib/api/scheduler";

interface Props {
  accounts: PublerAccount[];
  profiles: AccountProfile[];
  selectedIds: string[];
  onSelectionChange: (next: string[]) => void;
}

export function AccountsPicker({
  accounts,
  profiles,
  selectedIds,
  onSelectionChange,
}: Props) {
  const profileMap = useMemo(() => {
    const m = new Map<string, AccountProfile>();
    for (const p of profiles) m.set(p.publer_account_id, p);
    return m;
  }, [profiles]);

  const toggle = (id: string, disabled: boolean) => {
    if (disabled) return;
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((x) => x !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  if (accounts.length === 0) {
    return (
      <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
        <div className="display-serif text-xl text-[color:var(--paper)]">
          Нет подключённых аккаунтов
        </div>
        <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
          Подключи Instagram/YouTube в Publer workspace и настрой профиль.
        </p>
        <Link
          to="/scheduler/accounts"
          className="mt-3 rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
        >
          Открыть настройки
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
          аккаунтов · {accounts.length} · выбрано · {selectedIds.length}
        </span>
        <Link
          to="/scheduler/accounts"
          className="mono rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[11px] uppercase tracking-[0.1em] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
        >
          Настроить профили →
        </Link>
      </div>

      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {accounts.map((acc) => {
          const profile = profileMap.get(acc.id) ?? null;
          const hasProfile = profile !== null;
          const disabled = !hasProfile;
          const checked = selectedIds.includes(acc.id);
          const displayName = profile?.display_name ?? acc.name ?? acc.id;
          const network =
            profile?.network ?? (acc.provider || acc.type || "—");

          return (
            <li key={acc.id}>
              <label
                className={`surface-card flex cursor-pointer items-start gap-3 p-4 transition-colors ${
                  disabled
                    ? "cursor-not-allowed opacity-60"
                    : "hover:border-[color:var(--gold)]"
                } ${checked ? "border-[color:var(--gold)]" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={() => toggle(acc.id, disabled)}
                  className="mt-1 h-4 w-4 cursor-pointer accent-[color:var(--gold)] disabled:cursor-not-allowed"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <span className="display-serif truncate text-base text-[color:var(--paper)]">
                      {displayName}
                    </span>
                    <span
                      className="mono shrink-0 rounded-none border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                      style={{
                        color: "var(--mute-2)",
                        borderColor: "var(--line)",
                      }}
                    >
                      {network}
                    </span>
                  </div>
                  <div className="mono truncate text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                    id · {acc.id}
                    {acc.status ? ` · ${acc.status}` : ""}
                  </div>
                  {hasProfile ? (
                    <span
                      className="mono mt-1 inline-block w-fit rounded-none border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                      style={{
                        color: "var(--gold)",
                        borderColor: "var(--gold)",
                      }}
                    >
                      профиль задан
                    </span>
                  ) : (
                    <span className="mt-1 inline-block w-fit text-[11px] text-[color:var(--danger)]">
                      Настрой профиль — без него caption не сгенерируется
                    </span>
                  )}
                </div>
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
