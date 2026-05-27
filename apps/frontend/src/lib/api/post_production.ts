import { request } from "./core";

export interface VideoAsset {
  id: number;
  name: string;
  file_path: string;
  file_size_bytes: number;
  duration_sec: number;
  width: number;
  height: number;
  fps: number;
  video_codec: string;
  audio_codec: string | null;
  sample_rate: number | null;
  channels: number | null;
  created_at: string;
}

export const SPLIT_SCREEN_PANEL_FIT_MODES = ["fill", "fit", "manual"] as const;
export type SplitScreenPanelFitMode =
  (typeof SPLIT_SCREEN_PANEL_FIT_MODES)[number];

export interface SplitScreenTransform {
  x_pct: number;
  y_pct: number;
  width_pct: number;
  height_pct: number;
}

export interface SplitScreenConfig {
  enabled: boolean;
  companion_path: string | null;
  main_fit_mode: SplitScreenPanelFitMode;
  companion_fit_mode: SplitScreenPanelFitMode;
  split_ratio: number;
  main_transform: SplitScreenTransform;
  companion_transform: SplitScreenTransform;
}

export const DEFAULT_SPLIT_SCREEN: SplitScreenConfig = {
  enabled: false,
  companion_path: null,
  main_fit_mode: "fill",
  companion_fit_mode: "fill",
  split_ratio: 50,
  main_transform: { x_pct: 0, y_pct: 0, width_pct: 100, height_pct: 50 },
  companion_transform: { x_pct: 0, y_pct: 50, width_pct: 100, height_pct: 50 },
};

export interface PostProductionConfig {
  intro_path: string | null;
  outro_path: string | null;
  audio_normalize_enabled: boolean;
  audio_target_lufs: number;
  zoom_enabled: boolean;
  zoom_close_percent: number;
  zoom_medium_percent: number;
  zoom_wide_percent: number;
  zoom_apply_every_nth_cut: number;
  zoom_min_interval_sec: number;
  zoom_long_segment_threshold_sec: number;
  zoom_subsegment_min_sec: number;
  zoom_subsegment_max_sec: number;
  zoom_alternating_planes_enabled: boolean;
  bw_enabled: boolean;
  split_screen: SplitScreenConfig;
}

export const DEFAULT_POST_PRODUCTION_CONFIG: PostProductionConfig = {
  intro_path: null,
  outro_path: null,
  audio_normalize_enabled: true,
  audio_target_lufs: -14.0,
  zoom_enabled: false,
  zoom_close_percent: 30,
  zoom_medium_percent: 15,
  zoom_wide_percent: 0,
  zoom_apply_every_nth_cut: 1,
  zoom_min_interval_sec: 5.0,
  zoom_long_segment_threshold_sec: 6.0,
  zoom_subsegment_min_sec: 4.0,
  zoom_subsegment_max_sec: 7.0,
  zoom_alternating_planes_enabled: true,
  bw_enabled: false,
  split_screen: DEFAULT_SPLIT_SCREEN,
};

export interface PostProductionPreset {
  id: number;
  name: string;
  is_default: boolean;
  intro_asset_id: number | null;
  outro_asset_id: number | null;
  companion_asset_id: number | null;
  intro_asset: VideoAsset | null;
  outro_asset: VideoAsset | null;
  companion_asset: VideoAsset | null;
  config: PostProductionConfig;
  created_at: string;
  updated_at: string;
}

export interface PostProductionPresetCreatePayload {
  name: string;
  is_default?: boolean;
  intro_asset_id?: number | null;
  outro_asset_id?: number | null;
  companion_asset_id?: number | null;
  config?: PostProductionConfig;
}

export interface PostProductionPresetUpdatePayload {
  name?: string;
  is_default?: boolean;
  intro_asset_id?: number | null;
  outro_asset_id?: number | null;
  companion_asset_id?: number | null;
  config?: PostProductionConfig;
}

export interface AssetImportResponse {
  asset: VideoAsset;
  created: boolean;
}

export const postProductionApi = {
  listAssets: () => request<VideoAsset[]>("/api/v1/post_production/assets"),
  getAsset: (id: number) =>
    request<VideoAsset>(`/api/v1/post_production/assets/${id}`),
  importAsset: (form: FormData) =>
    request<AssetImportResponse>("/api/v1/post_production/assets", {
      method: "POST",
      body: form,
    }),
  deleteAsset: (id: number) =>
    request<void>(`/api/v1/post_production/assets/${id}`, {
      method: "DELETE",
    }),
  listPostProductionPresets: () =>
    request<PostProductionPreset[]>("/api/v1/post_production/presets"),
  getPostProductionPreset: (id: number) =>
    request<PostProductionPreset>(`/api/v1/post_production/presets/${id}`),
  getDefaultPostProductionPreset: () =>
    request<PostProductionPreset | null>(
      "/api/v1/post_production/presets/default",
    ),
  createPostProductionPreset: (payload: PostProductionPresetCreatePayload) =>
    request<PostProductionPreset>("/api/v1/post_production/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updatePostProductionPreset: (
    id: number,
    payload: PostProductionPresetUpdatePayload,
  ) =>
    request<PostProductionPreset>(`/api/v1/post_production/presets/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deletePostProductionPreset: (id: number) =>
    request<void>(`/api/v1/post_production/presets/${id}`, {
      method: "DELETE",
    }),
};
