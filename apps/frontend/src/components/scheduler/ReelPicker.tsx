
import { useMemo, useState } from "react";
import type { LikedReelRef } from "@/lib/api/scheduler";
import type { Project } from "@/lib/api/projects";

interface Props {
  reels: LikedReelRef[];
  projects: Project[];
  selectedIds: number[];
  onSelectionChange: (next: number[]) => void;
}

function formatDate(iso: string): string {
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

function getHook(meta: Record<string, unknown>): string {
  const raw =
    (meta?.hook as string | undefined) ??
    (meta?.title as string | undefined) ??
    (meta?.caption as string | undefined) ??
    "";
  if (typeof raw !== "string") return "";
  return raw.trim();
}

function getDurationSec(meta: Record<string, unknown>): number | null {
  const d =
    (meta?.duration_sec as number | undefined) ??
    (meta?.duration as number | undefined);
  return typeof d === "number" && Number.isFinite(d) ? d : null;
}

function getProjectId(meta: Record<string, unknown>): number | null {
  const pid = meta?.project_id;
  return typeof pid === "number" ? pid : null;
}

export function ReelPicker({
  reels,
  projects,
  selectedIds,
  onSelectionChange,
}: Props) {
  const [projectFilter, setProjectFilter] = useState<string>("all");
  const [jobFilter, setJobFilter] = useState<string>("all");

  const jobIds = useMemo(() => {
    const s = new Set<string>();
    for (const r of reels) s.add(r.job_id);
    return Array.from(s).sort();
  }, [reels]);

  const visible = useMemo(() => {
    return reels.filter((r) => {
      if (jobFilter !== "all" && r.job_id !== jobFilter) return false;
      if (projectFilter !== "all") {
        const pid = getProjectId(r.meta);
        if (pid === null) return false;
        if (String(pid) !== projectFilter) return false;
      }
      return true;
    });
  }, [reels, jobFilter, projectFilter]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const visibleIds = useMemo(() => visible.map((r) => r.id), [visible]);
  const visibleIdSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selectedSet.has(id));

  const toggle = (id: number) => {
    if (selectedSet.has(id)) {
      onSelectionChange(selectedIds.filter((x) => x !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const toggleAllVisible = () => {
    if (allVisibleSelected) {
      onSelectionChange(selectedIds.filter((id) => !visibleIdSet.has(id)));
    } else {
      const merged = new Set(selectedIds);
      for (const id of visibleIds) merged.add(id);
      onSelectionChange(Array.from(merged));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            Проект
          </span>
          <select
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            className="min-w-[180px] rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
          >
            <option value="all">Все проекты</option>
            {projects.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            Job
          </span>
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="min-w-[200px] rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] px-3 py-2 text-[13px] text-[color:var(--paper)] outline-none transition-colors focus:border-[color:var(--gold)]"
          >
            <option value="all">Все задачи</option>
            {jobIds.map((jid) => (
              <option key={jid} value={jid}>
                {jid.slice(0, 8)}…
              </option>
            ))}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-3">
          <span className="mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
            видно · {visible.length} · выбрано · {selectedIds.length}
          </span>
          <button
            type="button"
            onClick={toggleAllVisible}
            disabled={visible.length === 0}
            className="rounded-md border border-[color:var(--line)] px-3 py-1.5 text-[12px] text-[color:var(--paper-dim)] transition-colors hover:text-[color:var(--paper)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {allVisibleSelected ? "Снять все видимые" : "Выбрать все видимые"}
          </button>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="surface-card flex flex-col items-center justify-center gap-2 p-10 text-center">
          <div className="display-serif text-xl text-[color:var(--paper)]">
            Лайкнутых рилсов пока нет
          </div>
          <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
            Открой нарезку, перейди в Tinder-режим и оцени рилсы — лайкнутые
            появятся здесь и пойдут в кампании.
          </p>
        </div>
      ) : (
        <div className="surface-card overflow-hidden">
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-[color:var(--ink)]">
                <tr className="mono border-b border-[color:var(--line)] text-[10px] uppercase tracking-[0.14em] text-[color:var(--mute-2)]">
                  <th className="w-10 px-3 py-2"></th>
                  <th className="px-3 py-2">id</th>
                  <th className="px-3 py-2">job</th>
                  <th className="px-3 py-2">hook</th>
                  <th className="px-3 py-2">длит.</th>
                  <th className="px-3 py-2">создан</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => {
                  const hook = getHook(r.meta);
                  const dur = getDurationSec(r.meta);
                  const checked = selectedSet.has(r.id);
                  return (
                    <tr
                      key={r.id}
                      onClick={() => toggle(r.id)}
                      className={`cursor-pointer border-b border-[color:var(--line)] transition-colors last:border-b-0 hover:bg-[color:var(--ink-2)] ${
                        checked ? "bg-[color:var(--ink-2)]" : ""
                      }`}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(r.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="h-4 w-4 cursor-pointer accent-[color:var(--gold)]"
                        />
                      </td>
                      <td className="mono px-3 py-2 text-[color:var(--paper-dim)]">
                        {r.id}
                      </td>
                      <td className="mono px-3 py-2 text-[color:var(--paper-dim)]">
                        {r.job_id.slice(0, 8)}…
                      </td>
                      <td className="px-3 py-2 text-[color:var(--paper)]">
                        <span className="line-clamp-1 max-w-[320px]">
                          {hook || "—"}
                        </span>
                      </td>
                      <td className="mono px-3 py-2 text-[color:var(--paper-dim)]">
                        {dur !== null ? `${dur.toFixed(1)}s` : "—"}
                      </td>
                      <td className="mono px-3 py-2 text-[color:var(--mute-2)]">
                        {formatDate(r.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
