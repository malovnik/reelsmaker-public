/**
 * Backward-compat facade for the API client.
 *
 * The implementation lives in `./api/*` split by domain (core / jobs /
 * subtitle / post_production / settings). New code should import directly
 * from the relevant domain module:
 *
 *   import { jobsApi, type JobRead } from "@/lib/api/jobs";
 *
 * This file re-exports the full surface so existing imports like
 * `import { api, ApiError, type JobRead } from "@/lib/api"` keep working.
 */

export * from "./api/index";
