import type { ScheduleAssignment } from "@/lib/api/scheduler";
import { Card } from "@/components/ui";
import { AssignmentActions, type AssignmentActionHandlers } from "./AssignmentActions";
import { AssignmentContentSummary, DeliveryError } from "./AssignmentContent";
import { DISPLAY_TZ, formatScheduledDisplay } from "./campaignTime";
import { StatusPill } from "./StatusPill";
import { assignmentStatusMeta, networkShort } from "./statusMeta";

interface Props extends AssignmentActionHandlers {
  assignments: ScheduleAssignment[];
}

const tzCity = DISPLAY_TZ.split("/")[1]?.replace("_", " ") ?? DISPLAY_TZ;

/**
 * Адаптивный список назначений: таблица на десктопе (md+), карточки на mobile.
 * Закрывает d5 §5c — «таблица ↔ карточки». Действия и статусы видимы всегда.
 */
export function AssignmentList({ assignments, ...handlers }: Props) {
  return (
    <>
      {/* Desktop: таблица */}
      <div className="hidden overflow-x-auto border border-[var(--line-soft)] bg-[var(--ink-2)] md:block">
        <table className="w-full min-w-[860px] border-collapse text-left">
          <thead>
            <tr className="border-b border-[var(--line)]">
              {["Рилс · сеть", `Время (${tzCity})`, "Статус", "Контент", "Действия"].map(
                (h) => (
                  <th
                    key={h}
                    className="mono px-4 py-3 text-[0.625rem] font-normal uppercase tracking-[0.14em] text-[var(--mute-2)]"
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => {
              const meta = assignmentStatusMeta(a.status);
              return (
                <tr
                  key={a.id}
                  className="border-b border-[var(--line-soft)] align-top last:border-b-0"
                >
                  <td className="px-4 py-4">
                    <div className="flex flex-col gap-1">
                      <span className="text-[0.8125rem] text-[var(--paper)]">
                        Рилс #{a.reel_artifact_id}
                      </span>
                      <span className="mono text-[0.6875rem] text-[var(--copper)]">
                        {networkShort(a.network)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span className="mono text-[0.75rem] text-[var(--paper)]">
                      {formatScheduledDisplay(a.scheduled_at_utc)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <StatusPill meta={meta} />
                    {a.error_message ? <DeliveryError text={a.error_message} /> : null}
                  </td>
                  <td className="max-w-[360px] px-4 py-4">
                    <AssignmentContentSummary a={a} />
                  </td>
                  <td className="px-4 py-4">
                    <AssignmentActions a={a} layout="column" {...handlers} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile: карточки */}
      <ul className="flex flex-col gap-4 md:hidden">
        {assignments.map((a) => {
          const meta = assignmentStatusMeta(a.status);
          return (
            <li key={a.id}>
              <Card dense>
                <div className="flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[0.9375rem] text-[var(--paper)]">
                        Рилс #{a.reel_artifact_id}
                      </span>
                      <span className="mono text-[0.6875rem] text-[var(--copper)]">
                        {networkShort(a.network)} · {formatScheduledDisplay(a.scheduled_at_utc)}
                      </span>
                    </div>
                    <StatusPill meta={meta} className="shrink-0" />
                  </div>
                  {a.error_message ? <DeliveryError text={a.error_message} /> : null}
                  <AssignmentContentSummary a={a} />
                  <AssignmentActions a={a} layout="row" {...handlers} />
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </>
  );
}
