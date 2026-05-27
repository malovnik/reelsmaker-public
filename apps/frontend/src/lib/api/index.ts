/**
 * Barrel re-export for the split API client.
 *
 * Domain modules:
 *   - core            — `request`, `resolveUrl`, `ApiError`, health endpoint
 *   - jobs            — Job/Artifact types, job lifecycle + reel endpoints
 *   - subtitle        — subtitle style types, fonts, subtitle presets
 *   - post_production — assets + post-production presets
 *   - settings        — performance, vision, models, prompts, vision profiles
 *
 * The aggregate `api` object below preserves backward compatibility with the
 * pre-split `@/lib/api` surface. New code should prefer domain-scoped imports
 * (e.g. `import { jobsApi } from "@/lib/api/jobs"`).
 */

export * from "./core";
export * from "./jobs";
export * from "./subtitle";
export * from "./post_production";
export * from "./settings";
export * from "./projects";
export * from "./scheduler";
export * from "./proxies";

import { coreApi } from "./core";
import { jobsApi } from "./jobs";
import { subtitleApi } from "./subtitle";
import { postProductionApi } from "./post_production";
import { settingsApi } from "./settings";
import { projectsApi } from "./projects";
import { schedulerApi } from "./scheduler";
import { proxiesApi } from "./proxies";

export const api = {
  ...coreApi,
  ...jobsApi,
  ...subtitleApi,
  ...postProductionApi,
  ...settingsApi,
  ...projectsApi,
  ...schedulerApi,
  ...proxiesApi,
} as const;
