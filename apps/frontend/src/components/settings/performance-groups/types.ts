import type { PerformanceSettings } from "@/lib/api";

export type PerfUpdate = <K extends keyof PerformanceSettings>(
  key: K,
  value: PerformanceSettings[K],
) => void;

export interface GroupProps {
  values: PerformanceSettings;
  update: PerfUpdate;
}
