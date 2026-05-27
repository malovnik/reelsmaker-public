
import { Group, NumberRow, SwitchRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

/**
 * Multi-arc variant A (2026-04-21).
 *
 * Включает новую архитектуру composer'а — отдельный arc для каждого
 * candidate_moment из canvas. По умолчанию выключено (legacy single-arc
 * flow, zero regression). Окна и минимум evidence управляют тем, как
 * фильтруются фрагменты вокруг центра каждого момента.
 */
export function MultiArcGroup({ values, update }: GroupProps) {
  const enabled = values.multi_arc_enabled;

  return (
    <Group title="Multi-arc режим (variant A)">
      <p className="text-[0.8125rem] leading-snug text-[var(--mute)]">
        Для каждого ключевого момента строится отдельная сюжетная арка.
        По умолчанию выключено — работает обычная единая сборка.
      </p>
      <SwitchRow
        id="multi_arc_enabled"
        label="Своя арка на каждый момент"
        hintKey="multi_arc_builder"
        checked={enabled}
        onChange={(v) => update("multi_arc_enabled", v)}
      />
      {enabled && (
        <div className="mt-4 flex flex-col gap-4 border-t border-[var(--line)] pt-4">
          <NumberRow
            id="multi_arc_window_sec"
            label="Окно evidence вокруг момента"
            hint="Полуокно вокруг центра candidate_moment для фильтрации evidence."
            value={values.multi_arc_window_sec}
            onChange={(v) => update("multi_arc_window_sec", v)}
            min={20}
            max={180}
            step={5}
            unit="сек"
          />
          <NumberRow
            id="multi_arc_window_fallback_sec"
            label="Расширенное окно при недоборе"
            hint="Используется, если при основном окне найдено меньше минимума evidence."
            value={values.multi_arc_window_fallback_sec}
            onChange={(v) => update("multi_arc_window_fallback_sec", v)}
            min={30}
            max={300}
            step={5}
            unit="сек"
          />
          <NumberRow
            id="multi_arc_min_evidence_per_moment"
            label="Минимум evidence для построения arc"
            hint="Если в окне меньше указанного числа evidence — момент пропускается."
            value={values.multi_arc_min_evidence_per_moment}
            onChange={(v) => update("multi_arc_min_evidence_per_moment", v)}
            min={2}
            max={30}
            step={1}
          />
        </div>
      )}
    </Group>
  );
}
