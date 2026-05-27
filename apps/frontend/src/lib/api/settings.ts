import { request } from "./core";
import type { VisionProfile } from "./jobs";

// ─────────────── Models / Prompts ───────────────

export interface ModelsInfo {
  available_providers: string[];
  available_transcribers: string[];
  defaults: Record<string, string>;
  available_llm_models: Record<string, string[]>;
}

export interface PromptPayload {
  key: string;
  content: string;
}

// ─────────────── Vision Profiles (agent masks) ───────────────

export const AGENT_NAMES = [
  "hook_hunter",
  "emotional_peak_finder",
  "humor_specialist",
  "dramatic_irony_scanner",
  "thesis_extractor",
  "motif_tracker",
] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

export interface ProfileMaskRead {
  profile: VisionProfile;
  enabled_agents: AgentName[];
  story_weight: number;
  visual_weight: number;
  dead_zone_norm: number;
  ema_alpha: number;
  rule_of_thirds_y_shift: number;
  is_customized: boolean;
}

export interface VisionProfileOverride {
  enabled_agents: AgentName[];
  story_weight: number;
  visual_weight: number;
  dead_zone_norm: number;
  ema_alpha: number;
  rule_of_thirds_y_shift: number;
}

// ─────────────── Vision Layer (Moondream 2 local GGUF) ───────────────

export interface VisionRuntimeSettings {
  enabled: boolean;
  frame_sample_rate_sec: number;
}

export type VisionBackend = "metal" | "cpu" | "unavailable";

export interface VisionHealthStatus {
  available: boolean;
  model_loaded: boolean;
  backend: VisionBackend;
  latency_ms: number;
  model_path: string | null;
  error: string | null;
}

export interface VisionSettingsResponse {
  settings: VisionRuntimeSettings;
  health: VisionHealthStatus;
  gguf_repo: string;
  gguf_file: string;
  mmproj_file: string;
}

// ─────────────── Performance Settings (v0.5 Cycle 4.5) ───────────────

export const COHERENCE_MODES = ["off", "reject", "resort"] as const;
export type CoherenceMode = (typeof COHERENCE_MODES)[number];

export const PIPELINE_MODES = ["automatic", "manual"] as const;
export type PipelineMode = (typeof PIPELINE_MODES)[number];

export const SNAP_STRATEGIES = ["off", "beat", "onset", "both"] as const;
export type SnapStrategy = (typeof SNAP_STRATEGIES)[number];

export const PACING_PROFILES = [
  "dynamic",
  "balanced",
  "mkbhd_clean",
  "documentary",
] as const;
export type PacingProfile = (typeof PACING_PROFILES)[number];

// T9 — стратегии композитора. "auto" = UI-значение по умолчанию, означает
// «не передавать override, advisor выберет сам». Остальные три — реальные
// значения composer_strategy в AutoConfig.
export const COMPOSER_STRATEGIES = [
  "auto",
  "tight_context",
  "balanced",
  "thematic_free",
] as const;
export type ComposerStrategy = (typeof COMPOSER_STRATEGIES)[number];

export interface PerformanceSettings {
  render_concurrency: number;
  proxy_enabled: boolean;
  proxy_max_dim: number;
  proxy_video_crf: number;
  proxy_video_maxrate_kbps: number;
  proxy_audio_bitrate_kbps: number;
  proxy_cache_max_gb: number;
  proxy_lock_timeout_sec: number;
  proxy_skip_height_le: number;
  proxy_skip_duration_lt_sec: number;
  proxy_skip_bitrate_lt_kbps: number;
  default_use_source_for_render: boolean;
  coherence_mode: CoherenceMode;
  coherence_threshold: number;
  // Fix 5 — heavy stage toggles + reel target override
  variants_generator_enabled: boolean;
  rhythm_critique_loop_enabled: boolean;
  reel_target_duration_sec: number;
  reel_target_pull_strength: "off" | "soft" | "hard";
  skip_complete_short_arcs: boolean;
  pause_compression_enabled: boolean;
  pause_compression_threshold_sec: number;
  pause_compression_keep_sec: number;
  breath_compression_enabled: boolean;
  breath_compression_threshold_sec: number;
  breath_compression_keep_sec: number;
  rhythm_aware_cuts_enabled: boolean;
  rhythm_aware_max_shift_sec: number;
  filler_removal_enabled: boolean;
  filler_removal_aggressive: boolean;
  filler_confidence_threshold: number;
  filler_edge_buffer_sec: number;
  reducer_ensemble_size: number;
  reducer_ensemble_veto: number;
  jl_cut_enabled: boolean;
  jl_cut_mode: "role_change" | "all_transitions";
  jl_cut_max_offset_sec: number;
  semantic_chunking_enabled: boolean;
  semantic_chunk_target_duration_sec: number;
  semantic_chunk_min_duration_sec: number;
  semantic_chunk_similarity_threshold: number;
  cross_chunk_reducer_enabled: boolean;
  cross_chunk_reducer_strictness: "soft" | "strict";
  llm_tier_profile: "fast" | "legacy";
  llm_lite_variant: "2_5" | "3_1";
  pipeline_llm_provider: "gemini" | "zhipu";
  cut_snap_enabled: boolean;
  cut_snap_window_sec: number;
  // T11 Automatic Mode
  pipeline_mode: PipelineMode;
  // Phase 6 + Phase 8 + Phase 9 (2026-04-22) — narrative architecture modes
  narrative_mode: "bottom_up" | "chaptered" | "map_reduce" | "viral_2026";
  // Phase 8 map-reduce tunables
  narrative_chunk_size_chars: number;
  narrative_chunk_overlap_chars: number;
  narrative_clips_per_chunk_target: number;
  narrative_chunk_parallel_max: number;
  // Multi-arc variant A (2026-04-21) — per-canvas-moment arcs
  multi_arc_enabled: boolean;
  multi_arc_window_sec: number;
  multi_arc_window_fallback_sec: number;
  multi_arc_min_evidence_per_moment: number;
  pacing_profile: PacingProfile;
  // T10.1 Punchline pause
  punchline_pause_enabled: boolean;
  punchline_pitch_drop_hz: number;
  punchline_hold_after_sec: number;
  // T10.2 Snap strategy (onset/beat/both/off)
  snap_strategy: SnapStrategy;
  onset_snap_max_shift_sec: number;
  // T10.3 Punch-in zoom
  punch_in_zoom_enabled: boolean;
  punch_in_zoom_scale: number;
  punch_in_zoom_probability: number;
  punch_in_zoom_hold_ms: number;
  // Phase 9 (2026-04-22) — face tracker opt-in (был hardcoded always-on)
  face_tracker_enabled: boolean;
  // T10.7 Ken Burns
  ken_burns_drift_enabled: boolean;
  ken_burns_scale_per_sec: number;
  ken_burns_max_scale: number;
  // Predictable reel count
  reel_count_enforce_floor_ceiling: boolean;
  reel_count_dedup_jaccard_threshold: number;
  // T6.1 Preference retrieval
  preference_retrieval_mode: "cosine" | "top_by_date";
  // T8.1-T8.3 Adaptive audio
  mouth_sound_removal_enabled: boolean;
  breath_classifier_enabled: boolean;
  context_aware_keep_sec_enabled: boolean;
  // T8.4-T8.5 Smart J/L chooser + adaptive leveller
  smart_jl_chooser_enabled: boolean;
  adaptive_leveller_enabled: boolean;
  // T2.8 Screencast auto-zoom + deictic trigger
  screencast_cursor_zoom_enabled: boolean;
  screencast_damping_profile:
    | "underdamped"
    | "critically_damped"
    | "overdamped";
  screencast_zoom_max_factor: number;
  deictic_zoom_enabled: boolean;
}

export const settingsApi = {
  // Models
  models: () => request<ModelsInfo>("/api/v1/settings/models"),
  // Prompts
  listPrompts: () =>
    request<{ prompts: PromptPayload[] }>("/api/v1/settings/prompts"),
  getPrompt: (key: string) =>
    request<PromptPayload>(`/api/v1/settings/prompts/${key}`),
  upsertPrompt: (key: string, content: string) =>
    request<PromptPayload>(`/api/v1/settings/prompts/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, content }),
    }),
  // Runtime performance settings
  getPerformanceSettings: () =>
    request<PerformanceSettings>("/api/v1/settings/performance"),
  updatePerformanceSettings: (payload: PerformanceSettings) =>
    request<PerformanceSettings>("/api/v1/settings/performance", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  // Vision layer (Moondream 2 local GGUF)
  getVisionSettings: () =>
    request<VisionSettingsResponse>("/api/v1/settings/vision"),
  updateVisionSettings: (payload: VisionRuntimeSettings) =>
    request<VisionRuntimeSettings>("/api/v1/settings/vision", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  // Vision profile overrides
  listVisionProfiles: () =>
    request<ProfileMaskRead[]>("/api/v1/settings/profiles"),
  getVisionProfile: (profile: VisionProfile) =>
    request<ProfileMaskRead>(`/api/v1/settings/profiles/${profile}`),
  updateVisionProfile: (
    profile: VisionProfile,
    payload: VisionProfileOverride,
  ) =>
    request<ProfileMaskRead>(`/api/v1/settings/profiles/${profile}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  resetVisionProfile: (profile: VisionProfile) =>
    request<ProfileMaskRead>(`/api/v1/settings/profiles/${profile}`, {
      method: "DELETE",
    }),
};
