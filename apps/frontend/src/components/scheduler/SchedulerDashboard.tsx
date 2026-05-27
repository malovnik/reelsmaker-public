import { Link } from "react-router-dom";
import { useCallback, useState } from "react";
import {
  schedulerApi,
  type ConnectionStatus,
  type ScheduleCampaign,
} from "@/lib/api/scheduler";
import { Button } from "@/components/ui";
import { useConfirm, useToast } from "@/contexts";
import { CampaignCard } from "./CampaignCard";

interface Props {
  initialStatus: ConnectionStatus | null;
  initialCampaigns: ScheduleCampaign[];
  initialError: string | null;
}

/** Честный баннер подключения Publer: точка-индикатор + рабочее место. */
function ConnectionBanner({
  status,
  onRefresh,
  refreshing,
}: {
  status: ConnectionStatus | null;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const ok = status?.ok === true;
  return (
    <section className="flex flex-col gap-4 border border-[var(--line-soft)] bg-[var(--ink-2)] p-6">
      <div className="flex items-center justify-between gap-3">
        <span className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          // Подключение Publer
        </span>
        <Button variant="secondary" size="sm" onClick={onRefresh} loading={refreshing}>
          Обновить
        </Button>
      </div>

      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1.5 size-2.5 shrink-0"
          style={{ backgroundColor: ok ? "var(--gold)" : "var(--danger)" }}
        />
        <div className="flex min-w-0 flex-col gap-1">
          <div className="display-serif text-lg text-[var(--paper)]">
            {ok ? "Publer на связи" : "Publer не отвечает"}
          </div>
          <div className="mono text-[0.6875rem] text-[var(--mute-2)]">
            {status?.workspace ? `рабочее место ${status.workspace}` : "рабочее место не задано"}
            {" · "}
            {status?.accounts_count != null
              ? `${status.accounts_count} аккаунтов`
              : "аккаунты не загружены"}
          </div>
          {!ok ? (
            <p className="mt-1 text-[0.8125rem] text-[var(--paper-dim)]">
              Аккаунты подключаются на стороне Publer. Откройте Publer, привяжите площадки
              и нажмите «Обновить».
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-[var(--line-soft)] pt-4">
        <Link
          to="/scheduler/accounts"
          className="mono inline-flex min-h-11 items-center rounded-none border border-[var(--line)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--paper-dim)] transition-colors hover:border-[var(--mute)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
        >
          Профили аккаунтов
        </Link>
        <Link
          to="/scheduler/presets"
          className="mono inline-flex min-h-11 items-center rounded-none border border-[var(--line)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--paper-dim)] transition-colors hover:border-[var(--mute)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
        >
          Шаблоны подписей
        </Link>
        <Link
          to="/scheduler/new"
          className="mono inline-flex min-h-11 items-center rounded-none border border-[var(--gold)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--gold)] transition-colors hover:bg-[var(--gold)] hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
        >
          ＋ Новая кампания
        </Link>
      </div>
    </section>
  );
}

export function SchedulerDashboard({
  initialStatus,
  initialCampaigns,
  initialError,
}: Props) {
  const toast = useToast();
  const confirm = useConfirm();
  const [status, setStatus] = useState<ConnectionStatus | null>(initialStatus);
  const [campaigns, setCampaigns] = useState<ScheduleCampaign[]>(initialCampaigns);
  const [refreshing, setRefreshing] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [loadError] = useState<string | null>(initialError);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [st, camps] = await Promise.all([
        schedulerApi.getConnectionStatus(),
        schedulerApi.listCampaigns(),
      ]);
      setStatus(st);
      setCampaigns(camps);
    } catch (err) {
      toast.showError(err);
    } finally {
      setRefreshing(false);
    }
  }, [toast]);

  const handleDelete = useCallback(
    async (c: ScheduleCampaign) => {
      const ok = await confirm({
        title: "Удалить кампанию?",
        description: `Кампания «${c.name}» и её план публикаций будут удалены. Уже опубликованные посты в соцсетях останутся.`,
        confirmLabel: "Удалить",
        destructive: true,
      });
      if (!ok) return;
      setDeletingId(c.id);
      try {
        await schedulerApi.deleteCampaign(c.id);
        setCampaigns((prev) => prev.filter((x) => x.id !== c.id));
        toast.success("Кампания удалена");
      } catch (err) {
        toast.showError(err);
      } finally {
        setDeletingId(null);
      }
    },
    [confirm, toast],
  );

  return (
    <div className="flex flex-col gap-8">
      <ConnectionBanner status={status} onRefresh={refresh} refreshing={refreshing} />

      {loadError ? (
        <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-4 text-[0.875rem] text-[var(--danger)]">
          Часть данных не загрузилась. Нажмите «Обновить» — попробуем ещё раз.
        </div>
      ) : null}

      <section className="flex flex-col gap-4">
        <div className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          // Кампании · {campaigns.length}
        </div>

        {campaigns.length === 0 ? (
          <div className="flex flex-col items-center gap-2 border border-[var(--line-soft)] bg-[var(--ink-2)] p-10 text-center">
            <div className="display-serif text-xl text-[var(--paper)]">Расписание пустое</div>
            <p className="max-w-md text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
              Соберите первую кампанию — мастер за четыре шага разложит лайкнутые рилсы
              по датам и площадкам.
            </p>
            <Link
              to="/scheduler/new"
              className="mono mt-2 inline-flex min-h-11 items-center rounded-none border border-[var(--gold)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--gold)] transition-colors hover:bg-[var(--gold)] hover:text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
            >
              ＋ Создать кампанию
            </Link>
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6">
            {campaigns.map((c) => (
              <li key={c.id} className="flex">
                <CampaignCard
                  campaign={c}
                  onDelete={handleDelete}
                  deleting={deletingId === c.id}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
