import { useState } from "react";
import type { ScheduleAssignment } from "@/lib/api/scheduler";

/** Подпись с разворотом длинного текста. */
export function CaptionPreview({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const isLong = text.length > 120;
  const shown = !isLong || open ? text : `${text.slice(0, 120)}…`;
  return (
    <div className="flex flex-col gap-1">
      <p className="whitespace-pre-wrap break-words text-[0.8125rem] leading-relaxed text-[var(--paper-dim)]">
        {shown || "—"}
      </p>
      {isLong ? (
        <button
          type="button"
          onClick={() => setOpen((p) => !p)}
          className="mono self-start text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)] transition-colors hover:text-[var(--paper)]"
        >
          {open ? "свернуть" : "показать целиком"}
        </button>
      ) : null}
    </div>
  );
}

/** Текст ошибки доставки (mono, chi-цвет) с разворотом. */
export function DeliveryError({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const isLong = text.length > 80;
  return (
    <div className="mt-1.5 flex max-w-[260px] flex-col gap-1">
      <div
        className={
          open || !isLong
            ? "mono whitespace-pre-wrap break-words text-[0.625rem] leading-snug text-[var(--danger)]"
            : "mono truncate text-[0.625rem] text-[var(--danger)]"
        }
        title={isLong ? text : undefined}
      >
        {open || !isLong ? text : `${text.slice(0, 80)}…`}
      </div>
      {isLong ? (
        <button
          type="button"
          onClick={() => setOpen((p) => !p)}
          className="mono self-start text-[0.625rem] uppercase tracking-[0.14em] text-[var(--mute-2)] transition-colors hover:text-[var(--paper)]"
        >
          {open ? "свернуть" : "развернуть"}
        </button>
      ) : null}
    </div>
  );
}

/** Сводка контента публикации: заголовок (Shorts) + подпись + хэштеги. */
export function AssignmentContentSummary({ a }: { a: ScheduleAssignment }) {
  return (
    <div className="flex flex-col gap-2">
      {a.network === "youtube" && a.title ? (
        <div className="text-[0.8125rem] font-medium text-[var(--paper)]">{a.title}</div>
      ) : null}
      <CaptionPreview text={a.caption} />
      {a.hashtags && a.hashtags.length > 0 ? (
        <div className="mono text-[0.6875rem] text-[var(--gold)]">
          {a.hashtags.map((h) => `#${h.replace(/^#+/, "")}`).join(" ")}
        </div>
      ) : null}
    </div>
  );
}
