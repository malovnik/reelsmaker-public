/**
 * Утилиты времени планировщика. Отображение в часовом поясе площадки
 * (Asia/Ho_Chi_Minh) + конверсия datetime-local ↔ UTC ISO.
 *
 * Вынесено из CampaignDetailClient при декомпозиции — чистые функции, без UI.
 */

export const DISPLAY_TZ = "Asia/Ho_Chi_Minh";

export function formatDate(iso: string): string {
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

export function formatScheduledDisplay(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    return d.toLocaleString("ru-RU", {
      timeZone: DISPLAY_TZ,
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return utcIso;
  }
}

/**
 * UTC ISO → значение для `<input type="datetime-local">`, прочитанное как
 * настенное время в `Asia/Ho_Chi_Minh`. Формат: `YYYY-MM-DDTHH:mm`.
 */
export function utcIsoToLocalInput(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: DISPLAY_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const pick = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
    return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}`;
  } catch {
    return "";
  }
}

/**
 * `datetime-local` (без tz) → UTC ISO, трактуя ввод как настенное время
 * в `Asia/Ho_Chi_Minh`.
 */
export function localInputToUtcIso(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local);
  if (!m) return null;
  const [, yStr, moStr, dStr, hStr, miStr] = m;
  const y = Number(yStr);
  const mo = Number(moStr);
  const d = Number(dStr);
  const h = Number(hStr);
  const mi = Number(miStr);
  const asIfUtc = Date.UTC(y, mo - 1, d, h, mi, 0);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: DISPLAY_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date(asIfUtc));
  const pick = (t: string) =>
    Number(parts.find((p) => p.type === t)?.value ?? "0");
  const displayed = Date.UTC(
    pick("year"),
    pick("month") - 1,
    pick("day"),
    pick("hour"),
    pick("minute"),
    pick("second"),
  );
  const offsetMs = displayed - asIfUtc;
  return new Date(asIfUtc - offsetMs).toISOString();
}
