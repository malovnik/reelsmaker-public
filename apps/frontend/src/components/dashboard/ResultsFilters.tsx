
import type { VisionProfile } from "@/lib/api";
import { VISION_PROFILES } from "@/lib/api";
import { PROFILE_LABELS } from "@/components/ProfileSelector";

export type SortBy = "newest" | "virality" | "duration";

interface Props {
  profileFilter: VisionProfile | "all";
  sortBy: SortBy;
  minViralScore: number;
  onProfileChange: (p: VisionProfile | "all") => void;
  onSortChange: (s: SortBy) => void;
  onMinViralChange: (n: number) => void;
}

const SORT_LABELS: Record<SortBy, string> = {
  newest: "Сначала новые",
  virality: "По virality score",
  duration: "По длительности",
};

export function ResultsFilters({
  profileFilter,
  sortBy,
  minViralScore,
  onProfileChange,
  onSortChange,
  onMinViralChange,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-3">
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        Фильтры
      </span>
      <label className="flex items-center gap-2 text-xs text-[color:var(--text-secondary)]">
        <span>Профиль</span>
        <select
          value={profileFilter}
          onChange={(e) => onProfileChange(e.target.value as VisionProfile | "all")}
          className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
        >
          <option value="all">Все профили</option>
          {VISION_PROFILES.map((p) => (
            <option key={p} value={p}>
              {PROFILE_LABELS[p] ?? p}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-xs text-[color:var(--text-secondary)]">
        <span>Сортировка</span>
        <select
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value as SortBy)}
          className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
        >
          {(Object.keys(SORT_LABELS) as SortBy[]).map((s) => (
            <option key={s} value={s}>
              {SORT_LABELS[s]}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-xs text-[color:var(--text-secondary)]">
        <span>Min virality</span>
        <input
          type="number"
          min={0}
          max={100}
          value={minViralScore}
          onChange={(e) => {
            const raw = Number(e.target.value);
            if (Number.isNaN(raw)) return;
            onMinViralChange(Math.max(0, Math.min(100, Math.round(raw))));
          }}
          className="w-16 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 text-center font-mono text-sm tabular-nums text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
        />
      </label>
    </div>
  );
}
