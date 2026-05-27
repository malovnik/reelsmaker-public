/**
 * Единый словарь статусов планировщика: символ + честный русский лейбл + цвет.
 *
 * Статусы по спеке d5 §5: ● Опубликовано (kinzoku) · ◐ В очереди (kogane) ·
 * ○ Ждёт (kasumi) · ⚠ Не отправилось (chi). Расширено под реальный набор
 * AssignmentStatus бэкенда. Цвета — токены, символы — для mono-меты.
 */
import type {
  AssignmentStatus,
  PublerNetwork,
  ScheduleCampaignStatus,
} from "@/lib/api/scheduler";

export interface StatusMeta {
  /** Короткий символ-маркер (mono). */
  symbol: string;
  /** Человеческий русский лейбл. */
  label: string;
  /** CSS-токен цвета. */
  color: string;
}

const ASSIGNMENT_META: Record<AssignmentStatus, StatusMeta> = {
  draft: { symbol: "○", label: "Черновик", color: "var(--mute-2)" },
  queued: { symbol: "◐", label: "В очереди", color: "var(--kogane)" },
  uploading: { symbol: "◐", label: "Загружается", color: "var(--kogane)" },
  scheduling: { symbol: "◐", label: "Планируется", color: "var(--kogane)" },
  scheduled: { symbol: "●", label: "Запланировано", color: "var(--gold)" },
  published: { symbol: "●", label: "Опубликовано", color: "var(--gold)" },
  failed: { symbol: "⚠", label: "Не отправилось", color: "var(--danger)" },
  cancelled: { symbol: "✕", label: "Снято", color: "var(--mute-2)" },
};

const CAMPAIGN_META: Record<ScheduleCampaignStatus, StatusMeta> = {
  draft: { symbol: "○", label: "Черновик", color: "var(--mute-2)" },
  approved: { symbol: "●", label: "В работе", color: "var(--gold)" },
  cancelled: { symbol: "✕", label: "Отменена", color: "var(--mute-2)" },
};

export function assignmentStatusMeta(status: AssignmentStatus): StatusMeta {
  return ASSIGNMENT_META[status] ?? { symbol: "·", label: status, color: "var(--mute-2)" };
}

export function campaignStatusMeta(status: ScheduleCampaignStatus): StatusMeta {
  return CAMPAIGN_META[status] ?? { symbol: "·", label: status, color: "var(--mute-2)" };
}

/** Порядок статусов для сводной разбивки. */
export const ASSIGNMENT_STATUS_ORDER: AssignmentStatus[] = [
  "draft",
  "queued",
  "uploading",
  "scheduling",
  "scheduled",
  "published",
  "failed",
  "cancelled",
];

const NETWORK_LABELS: Record<PublerNetwork, string> = {
  instagram: "Instagram Reels",
  youtube: "YouTube Shorts",
};

const NETWORK_SHORT: Record<PublerNetwork, string> = {
  instagram: "Reels",
  youtube: "Shorts",
};

export function networkLabel(network: PublerNetwork): string {
  return NETWORK_LABELS[network] ?? network;
}

export function networkShort(network: PublerNetwork): string {
  return NETWORK_SHORT[network] ?? network;
}
