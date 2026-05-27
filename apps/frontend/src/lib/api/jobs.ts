import { request, resolveUrl, ApiError } from "./core";
import type { SubtitleStyleConfig } from "./subtitle";

export type JobStatus =
  | "pending"
  | "running"
  | "done"
  | "error"
  | "cancelled";

export type JobStage =
  | "ingest"
  | "proxy_generate"
  | "transcribe"
  | "translate"
  | "silence_cut"
  | "analyze"
  | "render"
  | "finalize"
  | "done";

export const SOURCE_LANGUAGES = [
  "auto",
  "ru",
  "en",
  "de",
  "es",
  "fr",
  "it",
  "pt",
  "zh",
  "ja",
  "ko",
] as const;
export type SourceLanguage = (typeof SOURCE_LANGUAGES)[number];

export const FIT_MODES = ["fill", "fit"] as const;
export type FitMode = (typeof FIT_MODES)[number];

export const VISION_PROFILES = [
  "talking_head",
  "fashion",
  "travel",
  "screencast",
  "custom",
] as const;
export type VisionProfile = (typeof VISION_PROFILES)[number];

export interface ProfileMetrics {
  wpm: number;
  silence_ratio: number;
  face_coverage: number | null;
  duration_sec: number;
  word_count: number;
  vision_frames_sampled: number;
}

export interface ProfileSuggestion {
  profile: VisionProfile;
  confidence: number;
  reasons: string[];
  metrics: ProfileMetrics;
}

export type ArtifactKind =
  | "transcript"
  | "cleaned_transcript"
  | "reel_plan"
  | "reel_output"
  | "audio_extract"
  | "subtitles"
  | "log"
  | "project_graph"
  | "proxy";

export interface ArtifactRead {
  id: number;
  kind: ArtifactKind;
  path: string;
  meta: Record<string, unknown>;
  created_at: string;
}

/**
 * Per-job overrides на выбранный post_production preset.
 * Все поля default true (если опущены — не отключают ничего).
 * false = отключить соответствующую часть пресета для конкретного job.
 */
export interface PostProductionOverrides {
  enable_intro?: boolean;
  enable_outro?: boolean;
  enable_zoom?: boolean;
  enable_loudnorm?: boolean;
  enable_bw?: boolean;
}

export interface JobRead {
  id: string;
  source_filename: string;
  display_name: string | null;
  source_size_bytes: number;
  source_duration_sec: number | null;
  status: JobStatus;
  current_stage: JobStage | null;
  progress: number;
  message: string | null;
  error: string | null;
  transcriber: string;
  llm_provider: string;
  llm_model: string;
  target_aspect: string;
  fit_mode: string;
  source_language: string;
  detected_language: string | null;
  subtitle_style_json: SubtitleStyleConfig | null;
  target_reel_count: number | null;
  force_reingest: boolean;
  vision_profile: VisionProfile;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  stage_durations: Record<string, number> | null;
  total_generation_sec: number | null;
  avg_composite_score: number | null;
}

export interface AutoAnalyzeDecision {
  parameter: string;
  value: unknown;
  confidence: number;
  source: string;
  reasoning: string;
}

export interface AutoAnalyzeResponse {
  job_id: string;
  pacing_profile: string;
  snap_strategy: string;
  composer_strategy: string;
  pause_compression_enabled: boolean;
  pause_compression_threshold_sec: number;
  pause_compression_keep_sec: number;
  breath_compression_enabled: boolean;
  filler_words_removal_enabled: boolean;
  punchline_pause_enabled: boolean;
  punchline_hold_after_sec: number;
  punch_in_zoom_enabled: boolean;
  punch_in_zoom_scale: number;
  punch_in_zoom_probability: number;
  ken_burns_drift_enabled: boolean;
  ken_burns_scale_per_sec: number;
  coherence_threshold: number;
  rhythm_aware_cuts_enabled: boolean;
  meta_confidence: number;
  warnings: string[];
  decisions: AutoAnalyzeDecision[];
  llm_fallback_applied: boolean;
  audio_features: Record<string, number | string | string[]>;
}

export const jobsApi = {
  listJobs: (limit = 50) =>
    request<JobRead[]>(`/api/v1/jobs?limit=${limit}`),
  getJob: (id: string) => request<JobRead>(`/api/v1/jobs/${id}`),
  createJob: (form: FormData) =>
    request<JobRead>("/api/v1/jobs", { method: "POST", body: form }),
  updateJobProfile: (id: string, profile: VisionProfile) =>
    request<JobRead>(`/api/v1/jobs/${id}/profile`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    }),
  renameJob: (id: string, displayName: string | null) =>
    request<JobRead>(`/api/v1/jobs/${id}/rename`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    }),
  getProfileSuggestion: (id: string) =>
    request<ProfileSuggestion>(`/api/v1/jobs/${id}/profile/suggestion`),
  autoAnalyzeJob: (id: string) =>
    request<AutoAnalyzeResponse>(`/api/v1/jobs/${id}/auto-analyze`, {
      method: "POST",
    }),
  jobThumbnailUrl: (id: string) => `/api/v1/jobs/${id}/thumbnail`,
  listArtifacts: (id: string) =>
    request<ArtifactRead[]>(`/api/v1/jobs/${id}/artifacts`),
  updateArtifactLike: (
    jobId: string,
    artifactId: number,
    liked: "none" | "like" | "dislike",
  ) =>
    request<ArtifactRead>(
      `/api/v1/jobs/${jobId}/artifacts/${artifactId}/like`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ liked }),
      },
    ),
  deleteJob: async (
    jobId: string,
    purge: "soft" | "hard" | "nuke" = "soft",
  ): Promise<{
    purge: string;
    deleted_reels: number;
    kept_liked: number;
    nuked_paths?: string[];
  }> =>
    request(`/api/v1/jobs/${jobId}?purge=${purge}`, {
      method: "DELETE",
    }),
  saveReels: async (
    jobId: string,
    reelIds: number[],
  ): Promise<{
    saved_relative: string;
    folder: string;
    copied_files: number;
    reels: Array<Record<string, unknown>>;
  }> =>
    request(`/api/v1/jobs/${jobId}/saved`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reel_ids: reelIds }),
    }),
  deleteArtifact: (jobId: string, artifactId: number): Promise<void> =>
    request<void>(`/api/v1/jobs/${jobId}/artifacts/${artifactId}`, {
      method: "DELETE",
    }),
  // T3.4 captions editor — text/plain response, use raw fetch
  getReelSubtitles: async (jobId: string, reelId: string): Promise<string> => {
    const response = await fetch(
      resolveUrl(
        `/api/v1/jobs/${jobId}/reels/${encodeURIComponent(reelId)}/subtitles`,
      ),
      { headers: { Accept: "text/plain" }, cache: "no-store" },
    );
    if (!response.ok) {
      let detail: unknown = null;
      try {
        detail = await response.json();
      } catch {
        detail = await response.text();
      }
      throw new ApiError(response.status, detail);
    }
    return response.text();
  },
  updateReelSubtitles: (jobId: string, reelId: string, assContent: string) =>
    request<void>(
      `/api/v1/jobs/${jobId}/reels/${encodeURIComponent(reelId)}/subtitles`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ass_content: assContent }),
      },
    ),
  // T3.7 export dialog
  exportReel: (jobId: string, reelId: string, preset: string) =>
    request<{
      preset: string;
      bitrate_k: number;
      target_lufs: number;
      download_url: string;
    }>(
      `/api/v1/jobs/${jobId}/reels/${encodeURIComponent(reelId)}/export?preset=${encodeURIComponent(preset)}`,
      { method: "POST" },
    ),
};
