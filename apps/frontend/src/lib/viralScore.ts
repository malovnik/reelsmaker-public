/**
 * Pure composite-score для рилса. На v1 используем данные, которые точно есть в
 * `reel_output` artifact.meta: duration_sec + необязательные rhythm/visual/narrative
 * поля, если backend их положит (не обязательно). Возвращаем "доверительный" score:
 * если данных мало — ближе к нейтральному 70, не к 100.
 */
export interface ViralScoreInput {
  durationSec?: number;
  rhythmScore?: number; // 0..1 — глобальный pipeline rhythm
  visualScore?: number; // 0..1 — среднее visual_score сегментов
  narrativeScore?: number; // 0..1
  trendScore?: number; // 0..1 — количественное соответствие трендам
}

export interface ViralScoreBreakdown {
  score: number;
  parts: Array<{ label: string; value: number; weight: number }>;
  grade: "A" | "A-" | "B" | "B-" | "C";
  comment: string;
}

export function computeViralScore(input: ViralScoreInput): ViralScoreBreakdown {
  const durationFit = scoreDurationFit(input.durationSec);
  const rhythm =
    typeof input.rhythmScore === "number"
      ? clamp01(input.rhythmScore) * 100
      : 70;
  const visual =
    typeof input.visualScore === "number"
      ? clamp01(input.visualScore) * 100
      : 70;
  const narrative =
    typeof input.narrativeScore === "number"
      ? clamp01(input.narrativeScore) * 100
      : 70;
  const trend =
    typeof input.trendScore === "number"
      ? clamp01(input.trendScore) * 100
      : 70;

  const parts = [
    { label: "Длительность", value: round(durationFit), weight: 0.35 },
    { label: "Ритм", value: round(rhythm), weight: 0.25 },
    { label: "Картинка", value: round(visual), weight: 0.2 },
    { label: "История", value: round(narrative), weight: 0.15 },
    { label: "Тренды", value: round(trend), weight: 0.05 },
  ];

  const weighted =
    parts.reduce((acc, p) => acc + p.value * p.weight, 0) /
    parts.reduce((acc, p) => acc + p.weight, 0);

  const score = Math.max(0, Math.min(100, Math.round(weighted)));
  return {
    score,
    parts,
    grade: gradeFor(score),
    comment: commentFor(score, durationFit, input.durationSec),
  };
}

/** Идеальная длительность рилса — 30-60 секунд (данные Instagram Reels best practices).
 *  Ниже 15 и выше 90 — резкое падение до 60. */
function scoreDurationFit(sec?: number): number {
  if (typeof sec !== "number" || sec <= 0) return 70;
  if (sec < 10) return 55;
  if (sec < 20) return 78;
  if (sec < 30) return 92;
  if (sec <= 60) return 100;
  if (sec <= 90) return 92;
  if (sec <= 120) return 80;
  if (sec <= 180) return 68;
  return 55;
}

function gradeFor(score: number): ViralScoreBreakdown["grade"] {
  if (score >= 90) return "A";
  if (score >= 82) return "A-";
  if (score >= 70) return "B";
  if (score >= 60) return "B-";
  return "C";
}

function commentFor(
  score: number,
  durFit: number,
  durationSec?: number,
): string {
  if (score >= 90) return "Сильный рилс — длительность и ритм в точке.";
  if (score >= 82) return "Хороший кандидат, можно публиковать.";
  if (durationSec !== undefined && durationSec < 15) {
    return "Слишком короткий — зрители не успеют зацепиться.";
  }
  if (durationSec !== undefined && durationSec > 120) {
    return "Длиннее, чем ожидают в рилсах — подумай про сокращение.";
  }
  if (durFit < 80) return "Длительность далека от идеальной для рилсов.";
  return "Средний результат — проверь контекст и hook.";
}

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function round(v: number): number {
  return Math.round(v);
}

/** Вытаскивает ViralScoreInput из произвольного artifact meta.
 * Ключи — best-effort: если backend добавит proper scores позже, они сразу подхватятся. */
export function viralInputFromMeta(
  meta: Record<string, unknown>,
): ViralScoreInput {
  return {
    durationSec: asNumber(meta.duration_sec),
    rhythmScore: asNumber(meta.rhythm_score),
    visualScore: asNumber(meta.visual_score),
    narrativeScore: asNumber(meta.narrative_score),
    trendScore: asNumber(meta.trend_score),
  };
}

/** Если backend уже посчитал composite 0-100 — вернём его напрямую,
 *  иначе пересчитаем через `computeViralScore`. */
export function readBackendCompositeScore(
  meta: Record<string, unknown>,
): number | undefined {
  const composite = asNumber(meta.composite_score);
  if (composite === undefined) return undefined;
  return Math.max(0, Math.min(100, Math.round(composite)));
}

function asNumber(v: unknown): number | undefined {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return undefined;
}
