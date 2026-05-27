
import { useCallback, useMemo, useState, useTransition } from "react";
import { api, type JobRead, type VisionProfile } from "@/lib/api";
import { useConfirm, useToast } from "@/contexts";
import { JobCard } from "@/components/dashboard/JobCard";
import {
  FilterChipRow,
  type ProfileFilter,
} from "@/components/dashboard/FilterChipRow";
import {
  ResultsFilters,
  type SortBy,
} from "@/components/dashboard/ResultsFilters";

interface Props {
  jobs: JobRead[];
}

const ALL_PROFILES: VisionProfile[] = [
  "talking_head",
  "fashion",
  "travel",
  "screencast",
  "custom",
];

type ViewMode = "grid" | "list";
const VIEW_STORAGE_KEY = "reelibra.dashboard.view";

export function JobList({ jobs: initial }: Props) {
  const toast = useToast();
  const confirm = useConfirm();
  const [jobs, setJobs] = useState<JobRead[]>(initial);
  const [filter, setFilter] = useState<ProfileFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("newest");
  const [minViralScore, setMinViralScore] = useState<number>(0);
  const [view, setView] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return "grid";
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    return stored === "list" ? "list" : "grid";
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isPending, startTransition] = useTransition();

  const setViewPersisted = useCallback((next: ViewMode) => {
    setView(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    }
  }, []);

  const handleRename = useCallback(
    async (jobId: string, newName: string | null) => {
      try {
        const updated = await api.renameJob(jobId, newName);
        setJobs((prev) =>
          prev.map((j) => (j.id === jobId ? updated : j)),
        );
      } catch (exc) {
        toast.showError(exc);
      }
    },
    [toast],
  );

  const counts = useMemo<Record<ProfileFilter, number>>(() => {
    const base: Record<ProfileFilter, number> = {
      all: jobs.length,
      talking_head: 0,
      fashion: 0,
      travel: 0,
      screencast: 0,
      custom: 0,
    };
    for (const job of jobs) {
      const p = job.vision_profile as VisionProfile;
      if (ALL_PROFILES.includes(p)) {
        base[p] += 1;
      }
    }
    return base;
  }, [jobs]);

  const filtered = useMemo(() => {
    let list = filter === "all"
      ? jobs
      : jobs.filter((j) => j.vision_profile === filter);
    if (minViralScore > 0) {
      const threshold = minViralScore / 100;
      list = list.filter((j) => {
        const score = j.avg_composite_score;
        return typeof score === "number" && score >= threshold;
      });
    }
    const sorted = [...list];
    if (sortBy === "newest") {
      sorted.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    } else if (sortBy === "virality") {
      sorted.sort((a, b) => (b.avg_composite_score ?? -1) - (a.avg_composite_score ?? -1));
    } else if (sortBy === "duration") {
      sorted.sort((a, b) => (b.source_duration_sec ?? 0) - (a.source_duration_sec ?? 0));
    }
    return sorted;
  }, [jobs, filter, minViralScore, sortBy]);


  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const deleteSelected = useCallback(
    (purge: "soft" | "hard" | "nuke") => {
      if (selected.size === 0) return;
      const ids = [...selected];
      startTransition(async () => {
        const failures: string[] = [];
        await Promise.all(
          ids.map(async (id) => {
            try {
              await api.deleteJob(id, purge);
            } catch {
              failures.push(id);
            }
          }),
        );
        setJobs((prev) => prev.filter((j) => failures.includes(j.id) || !selected.has(j.id)));
        setSelected(new Set(failures));
        if (failures.length > 0) {
          toast.error(`Не обработали ${failures.length} из ${ids.length}`, {
            detail: "Часть нарезок осталась — попробуй ещё раз.",
          });
        } else {
          toast.success(`Готово: обработали ${ids.length} нарезок`);
        }
      });
    },
    [selected, toast],
  );

  if (jobs.length === 0) {
    return (
      <div className="surface-card flex flex-col items-center gap-3 border-dashed p-12 text-center">
        <div
          aria-hidden="true"
          className="flex size-12 items-center justify-center rounded-none bg-[color:var(--accent-primary-subtle)]"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
        </div>
        <h3 className="text-base font-medium text-[color:var(--text-primary)]">
          Пока ни одной нарезки
        </h3>
        <p className="max-w-sm text-sm text-[color:var(--text-secondary)]">
          Загрузи первое видео в форме выше — первая нарезка займёт около
          двух минут для короткого ролика.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <ResultsFilters
        profileFilter={filter}
        sortBy={sortBy}
        minViralScore={minViralScore}
        onProfileChange={setFilter}
        onSortChange={setSortBy}
        onMinViralChange={setMinViralScore}
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterChipRow value={filter} onChange={setFilter} counts={counts} />
        <div
          role="group"
          aria-label="Режим отображения"
          className="flex items-center gap-1 rounded-[4px] border border-[color:var(--line-soft)] p-1"
        >
          <button
            type="button"
            onClick={() => setViewPersisted("grid")}
            aria-pressed={view === "grid"}
            className={[
              "rounded-[3px] px-3 py-1 text-xs transition-colors",
              view === "grid"
                ? "bg-[color:var(--ink-3)] text-[color:var(--paper)]"
                : "text-[color:var(--mute-2)] hover:text-[color:var(--paper)]",
            ].join(" ")}
          >
            Плитка
          </button>
          <button
            type="button"
            onClick={() => setViewPersisted("list")}
            aria-pressed={view === "list"}
            className={[
              "rounded-[3px] px-3 py-1 text-xs transition-colors",
              view === "list"
                ? "bg-[color:var(--ink-3)] text-[color:var(--paper)]"
                : "text-[color:var(--mute-2)] hover:text-[color:var(--paper)]",
            ].join(" ")}
          >
            Список
          </button>
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="surface-card p-10 text-center text-sm text-[color:var(--text-secondary)]">
          В этой категории нарезок нет — переключись на «Все» либо загрузи
          новое видео сверху.
        </div>
      ) : (
        <div
          className={
            view === "grid"
              ? "grid grid-cols-1 gap-4 sm:grid-cols-2"
              : "flex flex-col gap-2"
          }
        >
          {filtered.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              isSelected={selected.has(job.id)}
              onToggleSelect={() => toggleSelect(job.id)}
              onRename={handleRename}
              compact={view === "list"}
            />
          ))}
        </div>
      )}

      {selected.size > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-6">
          <div className="pointer-events-auto flex flex-wrap items-center gap-3  border border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] px-4 py-2 backdrop-blur">
            <span className="text-xs text-[color:var(--text-secondary)]">
              Выбрано {selected.size}
            </span>
            <span className="h-4 w-px bg-[color:var(--border-default)]" aria-hidden="true" />
            <button
              type="button"
              onClick={clearSelection}
              className="text-xs text-[color:var(--text-muted)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              Снять
            </button>
            <button
              type="button"
              onClick={() => deleteSelected("soft")}
              disabled={isPending}
              className=" bg-[color:var(--surface-raised)] px-3 py-1 text-xs font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-sunken)] disabled:cursor-not-allowed disabled:opacity-60"
              title="Скрыть из галереи. Файлы и данные остаются на диске."
            >
              Скрыть из галереи
            </button>
            <button
              type="button"
              onClick={async () => {
                const ok = await confirm({
                  title: "Удалить лишние рилсы?",
                  description:
                    "Сотрём файлы всех не-лайкнутых рилсов выбранных нарезок. Отлайканные рилсы, рабочая копия и транскрипт сохранятся.",
                  confirmLabel: "Удалить лишние",
                  destructive: true,
                });
                if (ok) deleteSelected("hard");
              }}
              disabled={isPending}
              className=" bg-[color:var(--surface-sunken)] px-3 py-1 text-xs font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-raised)] disabled:cursor-not-allowed disabled:opacity-60"
              title="Удалить mp4 не-лайкнутых рилсов. Отлайканные остаются."
            >
              Удалить лишние рилсы
            </button>
            <button
              type="button"
              onClick={async () => {
                const ok = await confirm({
                  title: `Удалить ${selected.size} нарезок полностью?`,
                  description:
                    "Сотрём исходное видео, артефакты, рилсы и транскрипт — всё. Это необратимо.",
                  confirmLabel: "Удалить полностью",
                  destructive: true,
                });
                if (ok) deleteSelected("nuke");
              }}
              disabled={isPending}
              className="btn btn-danger px-4 py-1.5  disabled:cursor-not-allowed disabled:opacity-60"
              title="Удалить всё: исходник, артефакты, БД-запись. Необратимо."
            >
              Удалить полностью
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
