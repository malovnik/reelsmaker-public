import type {
  AccountProfile,
  LikedReelRef,
  PublerAccount,
  ScheduleDistributionMode,
} from "@/lib/api/scheduler";
import { SCHEDULER_TZ } from "@/lib/constants/scheduler";
import { Input } from "@/components/ui";

const MODE_LABEL: Record<ScheduleDistributionMode, string> = {
  per_date: "По датам вручную",
  single_day: "В один день",
  serial: "Серия каждые N дней",
};

function formatDateLabel(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

interface Props {
  campaignName: string;
  onNameChange: (next: string) => void;
  selectedReelIds: number[];
  selectedAccountIds: string[];
  mode: ScheduleDistributionMode;
  timeOfDay: string;
  dates: string[];
  singleDayDate: string;
  singleDayIntervalMin: number;
  serialStartDate: string;
  serialIntervalDays: number;
  accountsById: Map<string, PublerAccount>;
  profilesById: Map<string, AccountProfile>;
  reelsById: Map<number, LikedReelRef>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="mono text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
        {label}
      </span>
      <span className="display-serif text-3xl text-[var(--paper)]">{value}</span>
    </div>
  );
}

/** Шаг 4: имя кампании + сводка параметров перед созданием. */
export function WizardSummary({
  campaignName,
  onNameChange,
  selectedReelIds,
  selectedAccountIds,
  mode,
  timeOfDay,
  dates,
  singleDayDate,
  singleDayIntervalMin,
  serialStartDate,
  serialIntervalDays,
  accountsById,
  profilesById,
  reelsById,
}: Props) {
  const scheduleLine =
    mode === "per_date"
      ? `${dates.length} ${dates.length === 1 ? "дата" : "дат"}: ${dates
          .map(formatDateLabel)
          .join(", ")}`
      : mode === "single_day"
        ? `${formatDateLabel(singleDayDate)}, шаг ${singleDayIntervalMin} мин`
        : `с ${formatDateLabel(serialStartDate)}, шаг ${serialIntervalDays} ${
            serialIntervalDays === 1 ? "день" : "дн."
          }`;

  return (
    <div className="flex flex-col gap-6 border border-[var(--line-soft)] bg-[var(--ink-2)] p-6">
      <Input
        label="Название кампании"
        value={campaignName}
        onChange={(e) => onNameChange(e.target.value)}
      />

      <div className="grid grid-cols-3 gap-4">
        <Stat label="рилсов" value={selectedReelIds.length} />
        <Stat label="аккаунтов" value={selectedAccountIds.length} />
        <Stat
          label="публикаций"
          value={selectedReelIds.length * selectedAccountIds.length}
        />
      </div>

      <div className="flex flex-col gap-1 border-t border-[var(--line-soft)] pt-4">
        <span className="mono text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          режим · время · пояс
        </span>
        <span className="text-[0.9375rem] text-[var(--paper)]">
          {MODE_LABEL[mode]} · {timeOfDay} · {SCHEDULER_TZ} (+07)
        </span>
        <span className="text-[0.8125rem] text-[var(--mute-2)]">{scheduleLine}</span>
      </div>

      <div className="flex flex-col gap-2 border-t border-[var(--line-soft)] pt-4">
        <span className="mono text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          аккаунты
        </span>
        <ul className="flex flex-wrap gap-1.5">
          {selectedAccountIds.map((id) => {
            const label =
              profilesById.get(id)?.display_name ?? accountsById.get(id)?.name ?? id;
            return (
              <li
                key={id}
                className="mono rounded-none border border-[var(--line)] bg-[var(--ink)] px-2 py-1 text-[0.6875rem] text-[var(--paper)]"
              >
                {label}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex flex-col gap-2 border-t border-[var(--line-soft)] pt-4">
        <span className="mono text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)]">
          рилсы
        </span>
        <ul className="flex flex-wrap gap-1.5">
          {selectedReelIds.map((id) => {
            const r = reelsById.get(id);
            return (
              <li
                key={id}
                className="mono rounded-none border border-[var(--line)] bg-[var(--ink)] px-2 py-1 text-[0.6875rem] text-[var(--paper)]"
              >
                #{id}
                {r ? ` · ${r.job_id.slice(0, 6)}…` : ""}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
