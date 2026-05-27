import { Link } from "react-router-dom";
import type { ScheduleCampaign } from "@/lib/api/scheduler";
import { Button, Card } from "@/components/ui";
import { StatusPill } from "./StatusPill";
import { campaignStatusMeta } from "./statusMeta";
import { formatDate } from "./campaignTime";

interface Props {
  campaign: ScheduleCampaign;
  onDelete: (c: ScheduleCampaign) => void;
  deleting: boolean;
}

/** Карточка кампании в дашборде планировщика. Действия видимы всегда. */
export function CampaignCard({ campaign, onDelete, deleting }: Props) {
  const meta = campaignStatusMeta(campaign.status);
  const sorted = [...campaign.dates].sort();
  const first = sorted[0];
  const last = sorted[sorted.length - 1];

  return (
    <Card interactive className="flex w-full flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="display-serif truncate text-lg text-[var(--paper)]">
            {campaign.name}
          </h3>
          <div className="mono text-[0.6875rem] text-[var(--mute-2)]">
            {campaign.time_of_day} · {campaign.tz}
          </div>
        </div>
        <StatusPill meta={meta} className="shrink-0" />
      </div>

      <div className="text-[0.875rem] text-[var(--paper-dim)]">
        {campaign.dates.length} {campaign.dates.length === 1 ? "дата" : "дат"}
        {first ? (
          <>
            {" · "}
            {formatDate(first)}
            {last && last !== first ? ` — ${formatDate(last)}` : ""}
          </>
        ) : null}
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-[var(--line-soft)] pt-4">
        <Link
          to={`/scheduler/campaigns/${campaign.id}`}
          className="mono inline-flex min-h-11 items-center rounded-none border border-[var(--line)] px-4 text-[0.75rem] uppercase tracking-[0.1em] text-[var(--paper-dim)] transition-colors hover:border-[var(--mute)] hover:text-[var(--paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--gold)]"
        >
          Открыть
        </Link>
        <Button variant="danger" size="sm" onClick={() => onDelete(campaign)} loading={deleting}>
          Удалить
        </Button>
      </div>
    </Card>
  );
}
