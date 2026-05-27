
import { useMemo } from "react";

import type { JobRead } from "@/lib/api";

interface Props {
  jobs: JobRead[];
}

/**
 * Reelibra dashboard Hero — приветствие по времени + 4 метрики студии.
 * Данные агрегируются из уже-известных jobs (source_duration_sec, reel_count,
 * analysis_summary.stats).
 *
 * Handoff-reference: screen_dashboard.jsx (Референсы/).
 */
export function DashboardHero({ jobs }: Props) {
  const greeting = useMemo(() => buildGreeting(), []);
  const metrics = useMemo(() => aggregateMetrics(jobs), [jobs]);

  return (
    <section className="grid gap-8 lg:grid-cols-[1.3fr_1fr] lg:items-end lg:gap-12">
      <div>
        <div className="mono micro mute mb-5">
          {greeting.dateLine} · {greeting.timeLine}
        </div>
        <h1
          className="display-serif text-[clamp(2rem,1.6rem+2.5vw,4rem)]"
          style={{ fontWeight: 600, textWrap: "balance" as const }}
        >
          {greeting.title}
          <span className="block mt-3 text-[color:var(--mute-2)] text-[clamp(1.125rem,0.9rem+1vw,1.5rem)] font-normal tracking-tight">
            За последние сутки собрано{" "}
            <span className="tnum text-[color:var(--gold)]">
              {metrics.recentClips}
            </span>{" "}
            клип{pluralize(metrics.recentClips, "ов", "", "а")}.
          </span>
        </h1>
      </div>

      <div className="surface-card p-6 lg:p-7">
        <div className="divider mb-5">всего за всё время</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6">
          <Metric value={metrics.totalClips} label="клипов собрано" />
          <Metric
            value={`${metrics.avgScore}`}
            suffix="/100"
            label="средний балл"
          />
          <Metric
            value={metrics.sourceHours}
            suffix="ч"
            label="исходника обработано"
          />
          <Metric value={metrics.completedJobs} label="заданий завершено" />
        </div>
      </div>
    </section>
  );
}

function Metric({
  value,
  label,
  suffix,
}: {
  value: string | number;
  label: string;
  suffix?: string;
}) {
  return (
    <div>
      <div
        className="display-serif tnum text-[2rem] leading-none sm:text-[2.25rem] lg:text-[2.5rem]"
        style={{ fontWeight: 600 }}
      >
        {value}
        {suffix ? (
          <span className="mute text-[1.125rem] ml-0.5">{suffix}</span>
        ) : null}
      </div>
      <div className="mono micro mute mt-2.5">{label}</div>
    </div>
  );
}

interface Greeting {
  dateLine: string;
  timeLine: string;
  title: string;
}

function buildGreeting(): Greeting {
  const now = new Date();
  const hour = now.getHours();
  // Не "Доброй ночи / Добрый день" — генерик-приветствие банкомата.
  // Reelibra про нарезку, поэтому формулируем через действие.
  const greetName =
    hour < 6
      ? "Ночь — а ты ещё режешь."
      : hour < 12
        ? "Утро. Что нарезаем?"
        : hour < 18
          ? "День в разгаре."
          : "Вечер. Последние нарезки в очередь.";
  const dateLine = new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);
  const timeLine = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(now);
  return { dateLine, timeLine, title: greetName };
}

interface Metrics {
  totalClips: number;
  recentClips: number;
  avgScore: number;
  sourceHours: number;
  completedJobs: number;
}

function aggregateMetrics(jobs: JobRead[]): Metrics {
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  let totalClips = 0;
  let recentClips = 0;
  let sourceSec = 0;
  let completedJobs = 0;
  // T2.4: реальный avg_composite_score из backend (через JobRead.hoist из options).
  let scoreSum = 0;
  let scoredJobs = 0;
  for (const job of jobs) {
    if (job.status !== "done") continue;
    completedJobs += 1;
    const fallbackCount = estimateReelCount(job.source_duration_sec);
    const reelCount = job.target_reel_count ?? fallbackCount;
    totalClips += reelCount;
    const createdMs = Date.parse(job.created_at);
    if (Number.isFinite(createdMs) && createdMs >= dayAgo) {
      recentClips += reelCount;
    }
    if (typeof job.source_duration_sec === "number") {
      sourceSec += job.source_duration_sec;
    }
    if (typeof job.avg_composite_score === "number") {
      scoreSum += job.avg_composite_score;
      scoredJobs += 1;
    }
  }
  // Реальный средний. Для старых job'ов, собранных до T2.4, avg_composite_score
  // может быть null — они не учитываются в avgScore (но влияют на totalClips).
  // Если все job'ы без score — показываем 0 (UI скроет metric).
  const avgScore = scoredJobs > 0 ? Math.round(scoreSum / scoredJobs) : 0;
  const sourceHours = Math.round((sourceSec / 3600) * 10) / 10;
  return { totalClips, recentClips, avgScore, sourceHours, completedJobs };
}

function estimateReelCount(durationSec: number | null): number {
  if (!durationSec || durationSec <= 0) return 0;
  return Math.max(3, Math.round((durationSec / 60) * 0.6));
}

function pluralize(n: number, few: string, one: string, other: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return other;
  return few;
}
