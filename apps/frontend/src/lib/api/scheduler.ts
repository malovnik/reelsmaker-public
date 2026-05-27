/**
 * `/api/v1/scheduler` — Publer workspace + account profiles + caption presets +
 * scheduling campaigns + assignments + manual publish.
 *
 * Types mirror backend Pydantic DTOs in
 * `videomaker.api.routes.scheduler` (ConnectionStatus / AccountProfileRead /
 * AccountProfileUpsert / CaptionPresetRead / CaptionPresetCreate /
 * CaptionPresetUpdate / CampaignRead / CampaignDetail / CampaignCreate /
 * CampaignCreateResponse / CampaignApproveResponse / AssignmentRead /
 * AssignmentPatch / ManualPublishRequest) and Publer domain schema in
 * `videomaker.services.publer.schemas.PublerAccount`.
 *
 * Note on naming: backend `response_model` serializes JSON columns WITHOUT the
 * `_json` suffix (e.g. ORM `default_hashtags_json` → DTO `default_hashtags`).
 * We match the DTO, not the ORM column.
 */

import { request } from "./core";

// ────────────────────────── connection ──────────────────────────

export interface ConnectionStatus {
  ok: boolean;
  workspace: string | null;
  accounts_count: number | null;
  error: string | null;
}

// ────────────────────────── accounts (live Publer) ──────────────────────────

export interface PublerAccount {
  id: string;
  provider: string;
  type: string | null;
  name: string | null;
  status: string | null;
}

// ────────────────────────── account profiles (local ORM) ──────────────────────────

export type PublerNetwork = "instagram" | "youtube";

export interface AccountProfile {
  publer_account_id: string;
  display_name: string;
  network: PublerNetwork;
  language: string;
  audience: string;
  tone: string;
  default_hashtags: string[];
  banned_words: string[];
  cta_style: string;
  max_caption_length: number;
  created_at: string;
  updated_at: string;
}

export interface AccountProfileUpsert {
  display_name: string;
  network: PublerNetwork;
  language?: string | null;
  audience?: string | null;
  tone?: string | null;
  default_hashtags?: string[] | null;
  banned_words?: string[] | null;
  cta_style?: string | null;
  max_caption_length?: number | null;
}

// ────────────────────────── caption presets ──────────────────────────

export type CaptionPresetPosition = "prepend" | "append";

export interface CaptionPreset {
  id: number;
  name: string;
  position: CaptionPresetPosition;
  content: string;
  account_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CaptionPresetCreate {
  name: string;
  position: CaptionPresetPosition;
  content: string;
  account_id?: string | null;
}

export interface CaptionPresetUpdate {
  name?: string;
  position?: CaptionPresetPosition;
  content?: string;
  account_id?: string | null;
  is_active?: boolean;
}

// ────────────────────────── campaigns ──────────────────────────

export type ScheduleCampaignStatus = "draft" | "approved" | "cancelled";

export interface ScheduleCampaign {
  id: number;
  name: string;
  tz: string;
  time_of_day: string;
  dates: string[];
  status: ScheduleCampaignStatus;
  created_at: string;
  updated_at: string;
}

export type ScheduleDistributionMode = "per_date" | "single_day" | "serial";

export interface ScheduleCampaignCreate {
  name: string;
  time_of_day: string;
  tz?: string;
  reel_artifact_ids: number[];
  account_ids: string[];
  mode: ScheduleDistributionMode;
  dates?: string[];
  single_day_date?: string;
  single_day_interval_min?: number;
  serial_start_date?: string;
  serial_interval_days?: number;
}

// ────────────────────────── assignments ──────────────────────────

export type AssignmentStatus =
  | "draft"
  | "queued"
  | "uploading"
  | "scheduling"
  | "scheduled"
  | "published"
  | "failed"
  | "cancelled";

export interface ScheduleAssignment {
  id: number;
  campaign_id: number;
  job_id: string;
  reel_artifact_id: number;
  publer_account_id: string;
  network: PublerNetwork;
  title: string;
  caption: string;
  hashtags: string[];
  applied_preset_ids: number[];
  scheduled_at_utc: string;
  status: AssignmentStatus;
  publer_media_id: string | null;
  publer_job_id: string | null;
  publer_post_id: string | null;
  publer_post_url: string | null;
  error_message: string | null;
  attempts: number;
  last_attempt_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssignmentUpdate {
  caption?: string;
  title?: string;
  hashtags?: string[];
  scheduled_at_utc?: string;
}

export interface CampaignCreateResponse {
  campaign: ScheduleCampaign;
  assignments: ScheduleAssignment[];
}

export interface CampaignDetail extends ScheduleCampaign {
  assignments: ScheduleAssignment[];
}

export interface CampaignApproveResponse {
  campaign_id: number;
  approved_count: number;
}

// ────────────────────────── manual publish ──────────────────────────

export interface ManualPublishRequest {
  reel_artifact_id: number;
  job_id: string;
  publer_account_id: string;
  scheduled_at_utc: string;
  custom_caption?: string | null;
  custom_title?: string | null;
}

// ────────────────────────── liked reels pool ──────────────────────────

/**
 * Subset of `ArtifactRead` returned by `GET /api/v1/jobs/artifacts/liked`
 * (scheduler UI pool of reel candidates). Full shape is re-exported from
 * `./jobs` as `ArtifactRead`; we re-declare a narrow alias for readability.
 */
export interface LikedReelRef {
  id: number;
  job_id: string;
  kind: string;
  path: string;
  meta: Record<string, unknown>;
  created_at: string;
}

// ────────────────────────── functions ──────────────────────────

function withQuery(path: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export const schedulerApi = {
  // connection
  getConnectionStatus: () =>
    request<ConnectionStatus>("/api/v1/scheduler/connection/status"),

  // live Publer accounts
  listPublerAccounts: () =>
    request<PublerAccount[]>("/api/v1/scheduler/accounts"),

  // account profiles (local ORM)
  listProfiles: () =>
    request<AccountProfile[]>("/api/v1/scheduler/accounts/profiles"),

  upsertProfile: (publerAccountId: string, payload: AccountProfileUpsert) =>
    request<AccountProfile>(
      `/api/v1/scheduler/accounts/profiles/${encodeURIComponent(publerAccountId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),

  deleteProfile: (publerAccountId: string) =>
    request<void>(
      `/api/v1/scheduler/accounts/profiles/${encodeURIComponent(publerAccountId)}`,
      { method: "DELETE" },
    ),

  // caption presets
  listPresets: (accountId?: string | null) => {
    const params = new URLSearchParams();
    if (accountId) params.set("account_id", accountId);
    return request<CaptionPreset[]>(
      withQuery("/api/v1/scheduler/presets", params),
    );
  },

  createPreset: (payload: CaptionPresetCreate) =>
    request<CaptionPreset>("/api/v1/scheduler/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  updatePreset: (id: number, payload: CaptionPresetUpdate) =>
    request<CaptionPreset>(`/api/v1/scheduler/presets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deletePreset: (id: number) =>
    request<void>(`/api/v1/scheduler/presets/${id}`, { method: "DELETE" }),

  // campaigns
  listCampaigns: (opts: { status?: ScheduleCampaignStatus | null; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.status) params.set("status_filter", opts.status);
    params.set("limit", String(opts.limit ?? 50));
    return request<ScheduleCampaign[]>(
      withQuery("/api/v1/scheduler/campaigns", params),
    );
  },

  createCampaign: (payload: ScheduleCampaignCreate) =>
    request<CampaignCreateResponse>("/api/v1/scheduler/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getCampaign: (id: number) =>
    request<CampaignDetail>(`/api/v1/scheduler/campaigns/${id}`),

  approveCampaign: (id: number) =>
    request<CampaignApproveResponse>(
      `/api/v1/scheduler/campaigns/${id}/approve`,
      { method: "POST" },
    ),

  deleteCampaign: (id: number) =>
    request<void>(`/api/v1/scheduler/campaigns/${id}`, { method: "DELETE" }),

  // assignments
  listAssignments: (
    opts: { campaignId?: number; status?: AssignmentStatus | null } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.campaignId !== undefined)
      params.set("campaign_id", String(opts.campaignId));
    if (opts.status) params.set("status_filter", opts.status);
    return request<ScheduleAssignment[]>(
      withQuery("/api/v1/scheduler/assignments", params),
    );
  },

  updateAssignment: (id: number, payload: AssignmentUpdate) =>
    request<ScheduleAssignment>(`/api/v1/scheduler/assignments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  cancelAssignment: (id: number) =>
    request<ScheduleAssignment>(
      `/api/v1/scheduler/assignments/${id}/cancel`,
      { method: "POST" },
    ),

  retryAssignment: (id: number) =>
    request<ScheduleAssignment>(
      `/api/v1/scheduler/assignments/${id}/retry`,
      { method: "POST" },
    ),

  // manual publish
  manualPublishOne: (payload: ManualPublishRequest) =>
    request<ScheduleAssignment>("/api/v1/scheduler/manual/publish-one", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  // liked reels pool (served under /jobs prefix, not /scheduler)
  listLikedReels: (
    opts: { projectId?: number; jobId?: string; limit?: number } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.projectId !== undefined)
      params.set("project_id", String(opts.projectId));
    if (opts.jobId) params.set("job_id", opts.jobId);
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    return request<LikedReelRef[]>(
      withQuery("/api/v1/jobs/artifacts/liked", params),
    );
  },
};
