
import { useCallback, useMemo, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "@/lib/router-compat";
import { api, type ArtifactRead } from "@/lib/api";
import { useToast } from "@/contexts";
import {
  computeViralScore,
  viralInputFromMeta,
} from "@/lib/viralScore";
import { ReelCard } from "@/components/job/ReelCard";

type ReelFilter = "all" | "top" | "short" | "long" | "like" | "dislike";

interface Props {
  jobId: string;
  reels: ArtifactRead[];
  onChange: (next: ArtifactRead[]) => void;
}

const FILTER_META: Record<ReelFilter, { label: string; hint: string }> = {
  all: { label: "Все", hint: "Все рилсы нарезки" },
  top: { label: "Топ", hint: "Оценка 90 и выше" },
  short: { label: "Короткие", hint: "Меньше 45 секунд" },
  long: { label: "Длинные", hint: "60 секунд и больше" },
  like: { label: "Нравятся", hint: "Отмеченные как понравившиеся" },
  dislike: { label: "Не нравятся", hint: "Отмеченные как не понравившиеся" },
};

const FILTER_ORDER: ReelFilter[] = ["all", "top", "short", "long", "like", "dislike"];

export function ReelGrid({ jobId, reels, onChange }: Props) {
  const toast = useToast();
  const router = useRouter();
  const [searchParams] = useSearchParams();
  const filterParam = searchParams.get("filter");
  const activeFilter: ReelFilter = FILTER_ORDER.includes(filterParam as ReelFilter)
    ? (filterParam as ReelFilter)
    : "all";

  const setFilter = useCallback(
    (next: ReelFilter) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === "all") params.delete("filter");
      else params.set("filter", next);
      const qs = params.toString();
      router.replace(qs ? `?${qs}` : "");
    },
    [router, searchParams],
  );

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [isPending, startTransition] = useTransition();

  const selectedCount = selected.size;
  const hasSelection = selectedCount > 0;

  const toggleSelect = useCallback((id: number) => {
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

  const updateReel = useCallback(
    (updated: ArtifactRead) => {
      onChange(reels.map((r) => (r.id === updated.id ? updated : r)));
    },
    [onChange, reels],
  );

  const deleteOne = useCallback(
    (id: number) => {
      startTransition(async () => {
        try {
          await api.deleteArtifact(jobId, id);
          onChange(reels.filter((r) => r.id !== id));
          setSelected((prev) => {
            if (!prev.has(id)) return prev;
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        } catch (exc) {
          toast.showError(exc);
        }
      });
    },
    [jobId, onChange, reels, toast],
  );

  const saveSelected = useCallback(() => {
    if (selected.size === 0) return;
    const ids = [...selected];
    startTransition(async () => {
      try {
        const summary = await api.saveReels(jobId, ids);
        toast.success(`Сохранено ${summary.copied_files} файлов`, {
          detail: `Папка saved/${summary.folder}/`,
        });
      } catch (exc) {
        toast.showError(exc);
      }
    });
  }, [jobId, selected, toast]);

  const deleteSelected = useCallback(() => {
    if (selected.size === 0) return;
    const ids = [...selected];
    startTransition(async () => {
      const failures: number[] = [];
      await Promise.all(
        ids.map(async (id) => {
          try {
            await api.deleteArtifact(jobId, id);
          } catch {
            failures.push(id);
          }
        }),
      );
      const failedSet = new Set(failures);
      onChange(reels.filter((r) => failedSet.has(r.id) || !selected.has(r.id)));
      setSelected(failedSet);
      if (failures.length > 0) {
        toast.error(
          `Не удалили ${failures.length} из ${ids.length}`,
          { detail: "Часть рилсов осталась — попробуй ещё раз." },
        );
      } else {
        toast.success(`Удалили ${ids.length} рилсов`);
      }
    });
  }, [jobId, onChange, reels, selected, toast]);

  const counts = useMemo<Record<ReelFilter, number>>(() => {
    const base: Record<ReelFilter, number> = {
      all: reels.length,
      top: 0,
      short: 0,
      long: 0,
      like: 0,
      dislike: 0,
    };
    for (const reel of reels) {
      const meta = reel.meta as Record<string, unknown>;
      const viral = computeViralScore(viralInputFromMeta(meta));
      const duration =
        typeof meta.duration_sec === "number" ? meta.duration_sec : 0;
      const liked = meta.liked === "like" || meta.liked === "dislike"
        ? (meta.liked as "like" | "dislike")
        : "none";
      if (viral.score >= 90) base.top += 1;
      if (duration > 0 && duration < 45) base.short += 1;
      if (duration >= 60) base.long += 1;
      if (liked === "like") base.like += 1;
      if (liked === "dislike") base.dislike += 1;
    }
    return base;
  }, [reels]);

  const filteredReels = useMemo(() => {
    if (activeFilter === "all") return reels;
    return reels.filter((reel) => {
      const meta = reel.meta as Record<string, unknown>;
      const viral = computeViralScore(viralInputFromMeta(meta));
      const duration =
        typeof meta.duration_sec === "number" ? meta.duration_sec : 0;
      const liked = meta.liked;
      switch (activeFilter) {
        case "top":
          return viral.score >= 90;
        case "short":
          return duration > 0 && duration < 45;
        case "long":
          return duration >= 60;
        case "like":
          return liked === "like";
        case "dislike":
          return liked === "dislike";
        default:
          return true;
      }
    });
  }, [activeFilter, reels]);

  const countLabel = useMemo(() => formatReelCount(reels.length), [reels.length]);

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
            Готовые рилсы
          </h2>
          <span className="font-mono text-xs text-[color:var(--text-muted)]">
            {countLabel}
          </span>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTER_ORDER.map((key) => {
          const meta = FILTER_META[key];
          const count = counts[key];
          const isActive = key === activeFilter;
          const disabled = count === 0 && key !== "all";
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              disabled={disabled}
              aria-pressed={isActive}
              title={meta.hint}
              className={`inline-flex items-center gap-1.5 rounded-none border px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                isActive
                  ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary)] text-[color:var(--accent-on-primary)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
              }`}
            >
              {meta.label}
              <span
                className={`font-mono text-[10px] tabular-nums ${
                  isActive ? "opacity-75" : "opacity-60"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {filteredReels.length === 0 ? (
        <div className="surface-card p-10 text-center text-sm text-[color:var(--text-secondary)]">
          В этой категории — никого. Открой «Все», там вся подборка.
        </div>
      ) : (
        // VD-02: рилсы 9:16 узкие — раскрываем галерею до 6 колонок на широких
        // экранах (1400px+). Плавная прогрессия 2→3→4→5→6.
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4 lg:gap-6 xl:grid-cols-5 2xl:grid-cols-6">
          {filteredReels.map((artifact) => (
            <ReelCard
              key={artifact.id}
              jobId={jobId}
              artifact={artifact}
              isSelected={selected.has(artifact.id)}
              onToggleSelect={() => toggleSelect(artifact.id)}
              onDelete={() => deleteOne(artifact.id)}
              onUpdate={updateReel}
              busy={isPending}
            />
          ))}
        </div>
      )}

      {hasSelection && (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-6">
          <div className="pointer-events-auto flex items-center gap-3 rounded-none border border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] px-4 py-2 shadow-[var(--shadow-lg)] backdrop-blur">
            <span className="text-xs text-[color:var(--text-secondary)]">
              Выбрано {formatReelCount(selectedCount)}
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
              onClick={saveSelected}
              disabled={isPending}
              className="rounded-none bg-[color:var(--surface-raised)] px-3 py-1 text-xs font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-sunken)] disabled:cursor-not-allowed disabled:opacity-60"
              title="Скопировать отобранные в подпапку saved/"
            >
              Сохранить в папку
            </button>
            <button
              type="button"
              onClick={deleteSelected}
              disabled={isPending}
              className="btn btn-danger px-4 py-1.5 rounded-none disabled:cursor-not-allowed disabled:opacity-60"
            >
              Удалить
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function formatReelCount(n: number): string {
  const mod100 = n % 100;
  const mod10 = n % 10;
  let suffix = "рилсов";
  if (mod100 < 11 || mod100 > 14) {
    if (mod10 === 1) suffix = "рилс";
    else if (mod10 >= 2 && mod10 <= 4) suffix = "рилса";
  }
  return `${n} ${suffix}`;
}
