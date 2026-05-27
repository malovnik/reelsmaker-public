
import { Link } from "react-router-dom";
import { useCallback, useState } from "react";
import {
  schedulerApi,
  type ConnectionStatus,
  type ScheduleCampaign,
} from "@/lib/api/scheduler";

interface Props {
  initialStatus: ConnectionStatus | null;
  initialCampaigns: ScheduleCampaign[];
  initialError: string | null;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function statusBadge(status: ScheduleCampaign["status"]): {
  label: string;
  color: string;
} {
  switch (status) {
    case "draft":
      return { label: "черновик", color: "var(--mute-2)" };
    case "approved":
      return { label: "в работе", color: "var(--gold)" };
    case "cancelled":
      return { label: "отменена", color: "var(--danger)" };
    default:
      return { label: status, color: "var(--mute-2)" };
  }
}

export function SchedulerDashboard({
  initialStatus,
  initialCampaigns,
  initialError,
}: Props) {
  const [status, setStatus] = useState<ConnectionStatus | null>(initialStatus);
  const [campaigns, setCampaigns] =
    useState<ScheduleCampaign[]>(initialCampaigns);
  const [error, setError] = useState<string | null>(initialError);
  const [refreshing, setRefreshing] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [st, camps] = await Promise.all([
        schedulerApi.getConnectionStatus(),
        schedulerApi.listCampaigns(),
      ]);
      setStatus(st);
      setCampaigns(camps);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setRefreshing(false);
    }
  }, []);

  const handleDelete = useCallback(
    async (c: ScheduleCampaign) => {
      if (
        !confirm(
          `Удалить кампанию «${c.name}»? Все назначения внутри будут удалены.`,
        )
      ) {
        return;
      }
      setDeletingId(c.id);
      try {
        await schedulerApi.deleteCampaign(c.id);
        setCampaigns((prev) => prev.filter((x) => x.id !== c.id));
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        setDeletingId(null);
      }
    },
    [],
  );

  const isOk = status?.ok === true;
  const dotColor = isOk ? "var(--gold)" : "var(--danger)";

  return (
    <div className="flex flex-col gap-6">
      <section className="surface-card flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            publer workspace
          </div>
          <button
            type="button"
            onClick={refresh}
            disabled={refreshing}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Обновляю…" : "Обновить"}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <span
            className="h-3 w-3 shrink-0 rounded-full"
            style={{ backgroundColor: dotColor }}
            aria-hidden
          />
          <div className="flex min-w-0 flex-col gap-1">
            <div className="display-serif text-xl text-[color:var(--paper)]">
              {isOk ? "Подключение активно" : "Publer недоступен"}
            </div>
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
              {status?.workspace ? `workspace · ${status.workspace}` : "workspace не задан"}
              {" · "}
              {status?.accounts_count !== null && status?.accounts_count !== undefined
                ? `accounts · ${status.accounts_count}`
                : "accounts · —"}
            </div>
            {status?.error ? (
              <div className="text-[12px] text-[color:var(--danger)]">
                {status.error}
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to="/scheduler/accounts"
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
          >
            Профили аккаунтов
          </Link>
          <Link
            to="/scheduler/presets"
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
          >
            Caption-пресеты
          </Link>
          <Link
            to="/scheduler/new"
            className="btn btn-primary"
          >
            + Новая кампания
          </Link>
        </div>
      </section>

      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]">
          {error}
        </div>
      ) : null}

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            кампании · {campaigns.length}
          </div>
        </div>

        {campaigns.length === 0 ? (
          <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
            <div className="display-serif text-2xl text-[color:var(--paper)]">
              Расписание пустое
            </div>
            <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
              Нажми «Новая кампания» — мастер за четыре шага соберёт публикации
              из лайкнутых рилсов и расставит их по датам.
            </p>
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {campaigns.map((c) => {
              const badge = statusBadge(c.status);
              const first = c.dates[0];
              const last = c.dates[c.dates.length - 1];
              return (
                <li
                  key={c.id}
                  className="surface-card flex flex-col gap-3 p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-col gap-1">
                      <div className="display-serif truncate text-xl text-[color:var(--paper)]">
                        {c.name}
                      </div>
                      <div className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                        id · {c.id} · {c.tz} · {c.time_of_day}
                      </div>
                    </div>
                    <span
                      className="mono shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em]"
                      style={{
                        color: badge.color,
                        borderColor: badge.color,
                      }}
                    >
                      {badge.label}
                    </span>
                  </div>

                  <div className="text-sm text-[color:var(--text-secondary)]">
                    {c.dates.length} {c.dates.length === 1 ? "дата" : "дат"}
                    {first ? (
                      <>
                        {" · "}
                        {formatDate(first)}
                        {last && last !== first ? ` — ${formatDate(last)}` : ""}
                      </>
                    ) : null}
                  </div>

                  <div className="mt-auto flex items-center gap-2 pt-2">
                    <Link
                      to={`/scheduler/campaigns/${c.id}`}
                      className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)]"
                    >
                      Открыть
                    </Link>
                    <button
                      type="button"
                      onClick={() => handleDelete(c)}
                      disabled={deletingId === c.id}
                      className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {deletingId === c.id ? "Удаляю…" : "Удалить"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
