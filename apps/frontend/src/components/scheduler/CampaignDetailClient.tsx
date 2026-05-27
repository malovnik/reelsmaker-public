import { Link } from "react-router-dom";
import { useRouter } from "@/lib/router-compat";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  schedulerApi,
  type AssignmentStatus,
  type CampaignDetail,
  type ScheduleAssignment,
} from "@/lib/api/scheduler";
import { ApiError } from "@/lib/api/core";
import { Button } from "@/components/ui";
import { useConfirm, useToast } from "@/contexts";
import { AssignmentEditModal } from "./AssignmentEditModal";
import { AssignmentList } from "./AssignmentList";
import { StatusPill } from "./StatusPill";
import {
  ASSIGNMENT_STATUS_ORDER,
  assignmentStatusMeta,
  campaignStatusMeta,
} from "./statusMeta";
import { formatDate } from "./campaignTime";

interface Props {
  initialCampaign: CampaignDetail;
}

/** Активна ли публикация (есть смысл поллить статус). */
const ACTIVE_STATUSES: AssignmentStatus[] = [
  "draft",
  "queued",
  "uploading",
  "scheduling",
];

export function CampaignDetailClient({ initialCampaign }: Props) {
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();

  const [campaign, setCampaign] = useState<CampaignDetail>(initialCampaign);
  const [refreshing, setRefreshing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<ScheduleAssignment | null>(null);

  const hasActive = useMemo(
    () => campaign.assignments.some((a) => ACTIVE_STATUSES.includes(a.status)),
    [campaign.assignments],
  );

  useEffect(() => {
    if (!hasActive || editing !== null) return;
    let cancelled = false;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await schedulerApi.getCampaign(campaign.id);
        if (!cancelled) setCampaign(next);
      } catch {
        // тихо — ручной «Обновить» покажет ошибку
      }
    };
    const id = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [campaign.id, hasActive, editing]);

  const breakdown = useMemo(() => {
    const counts = {} as Record<AssignmentStatus, number>;
    for (const s of ASSIGNMENT_STATUS_ORDER) counts[s] = 0;
    for (const a of campaign.assignments) counts[a.status] += 1;
    return counts;
  }, [campaign.assignments]);

  const patchAssignment = useCallback((updated: ScheduleAssignment) => {
    setCampaign((prev) => ({
      ...prev,
      assignments: prev.assignments.map((x) => (x.id === updated.id ? updated : x)),
    }));
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setCampaign(await schedulerApi.getCampaign(campaign.id));
    } catch (err) {
      toast.showError(err);
    } finally {
      setRefreshing(false);
    }
  }, [campaign.id, toast]);

  const handleApprove = useCallback(async () => {
    const ok = await confirm({
      title: "Одобрить кампанию?",
      description: `Все черновики «${campaign.name}» уйдут в очередь, и публикации начнут уходить в Publer по расписанию.`,
      confirmLabel: "Одобрить",
    });
    if (!ok) return;
    setApproving(true);
    try {
      await schedulerApi.approveCampaign(campaign.id);
      setCampaign(await schedulerApi.getCampaign(campaign.id));
      toast.success("Кампания одобрена — публикации в очереди");
    } catch (err) {
      toast.showError(err);
    } finally {
      setApproving(false);
    }
  }, [campaign.id, campaign.name, confirm, toast]);

  const handleDelete = useCallback(async () => {
    const ok = await confirm({
      title: "Удалить кампанию?",
      description: `Кампания «${campaign.name}» и все её публикации будут удалены. Уже опубликованные посты в соцсетях останутся — удаляется только план.`,
      confirmLabel: "Удалить",
      destructive: true,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await schedulerApi.deleteCampaign(campaign.id);
      toast.success("Кампания удалена");
      router.push("/scheduler");
      router.refresh();
    } catch (err) {
      toast.showError(err);
      setDeleting(false);
    }
  }, [campaign.id, campaign.name, confirm, router, toast]);

  const handleCancel = useCallback(
    async (a: ScheduleAssignment) => {
      const ok = await confirm({
        title: "Снять публикацию?",
        description:
          "Снимем её из очереди Publer, пока она не ушла. Если пост уже опубликован, снять его нельзя — открывайте и удаляйте в самой соцсети.",
        confirmLabel: "Снять",
        destructive: true,
      });
      if (!ok) return;
      setCancellingId(a.id);
      try {
        patchAssignment(await schedulerApi.cancelAssignment(a.id));
        toast.success("Публикация снята из очереди");
      } catch (err) {
        // Честная развилка: 409 — уже опубликовано (необратимо),
        // 502 — Publer недоступен (можно повторить позже).
        if (err instanceof ApiError && err.status === 409) {
          toast.error("Снять нельзя — пост уже опубликован", {
            detail:
              "Публикация ушла в соцсеть. Отозвать её отсюда невозможно — откройте пост и удалите его вручную.",
          });
        } else if (err instanceof ApiError && err.status === 502) {
          toast.error("Publer сейчас недоступен", {
            detail: "Снятие не выполнено. Попробуйте ещё раз через минуту.",
          });
        } else {
          toast.showError(err);
        }
      } finally {
        setCancellingId(null);
      }
    },
    [confirm, patchAssignment, toast],
  );

  const handleRetry = useCallback(
    async (a: ScheduleAssignment) => {
      setRetryingId(a.id);
      try {
        patchAssignment(await schedulerApi.retryAssignment(a.id));
        toast.success("Публикация снова в очереди");
      } catch (err) {
        toast.showError(err);
      } finally {
        setRetryingId(null);
      }
    },
    [patchAssignment, toast],
  );

  const handleSaved = useCallback(
    (updated: ScheduleAssignment) => {
      patchAssignment(updated);
      setEditing(null);
    },
    [patchAssignment],
  );

  const statusMeta = campaignStatusMeta(campaign.status);
  const datesSorted = [...campaign.dates].sort();
  const firstDate = datesSorted[0];
  const lastDate = datesSorted[datesSorted.length - 1];

  return (
    <div className="flex flex-col gap-8">
      <Link
        to="/scheduler"
        className="mono w-fit text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)] transition-colors hover:text-[var(--paper)]"
      >
        ← Кампании
      </Link>

      <header className="flex flex-col gap-5 border border-[var(--line-soft)] bg-[var(--ink-2)] p-6 md:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex min-w-0 flex-col gap-2">
            <div className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--copper)]">
              // Кампания
            </div>
            <h1 className="display-serif text-2xl leading-tight text-[var(--paper)] md:text-3xl">
              {campaign.name}
            </h1>
            <div className="mono text-[0.75rem] text-[var(--mute-2)]">
              {campaign.time_of_day} · {campaign.tz} ·{" "}
              {firstDate ? formatDate(firstDate) : "даты не заданы"}
              {lastDate && lastDate !== firstDate ? ` — ${formatDate(lastDate)}` : ""}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill meta={statusMeta} className="shrink-0" />
            <Button variant="secondary" size="sm" onClick={refresh} loading={refreshing}>
              Обновить
            </Button>
            {campaign.status === "draft" ? (
              <Button variant="primary" size="sm" onClick={handleApprove} loading={approving}>
                Одобрить всё
              </Button>
            ) : null}
            <Button variant="danger" size="sm" onClick={handleDelete} loading={deleting}>
              Удалить
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 border-t border-[var(--line-soft)] pt-4">
          {ASSIGNMENT_STATUS_ORDER.map((s) => {
            const count = breakdown[s];
            if (count === 0) return null;
            return <StatusPill key={s} meta={assignmentStatusMeta(s)} count={count} />;
          })}
        </div>
      </header>

      <section className="flex flex-col gap-4">
        <div className="mono text-[0.6875rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          // Публикации · {campaign.assignments.length}
        </div>

        {campaign.assignments.length === 0 ? (
          <div className="flex flex-col items-center gap-2 border border-[var(--line-soft)] bg-[var(--ink-2)] p-10 text-center">
            <div className="display-serif text-xl text-[var(--paper)]">Публикаций пока нет</div>
            <p className="text-[0.9375rem] text-[var(--mute-2)]">
              В этой кампании ещё не собрано ни одного назначения.
            </p>
          </div>
        ) : (
          <AssignmentList
            assignments={campaign.assignments}
            onEdit={setEditing}
            onCancel={handleCancel}
            onRetry={handleRetry}
            cancellingId={cancellingId}
            retryingId={retryingId}
          />
        )}
      </section>

      <AssignmentEditModal
        open={editing !== null}
        assignment={editing}
        onClose={() => setEditing(null)}
        onSaved={handleSaved}
      />
    </div>
  );
}
