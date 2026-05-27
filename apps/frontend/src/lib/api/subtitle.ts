import { request } from "./core";

export const SUBTITLE_ANCHORS = ["top", "center", "bottom"] as const;
export type SubtitleAnchor = (typeof SUBTITLE_ANCHORS)[number];

export const FONT_WEIGHTS = ["regular", "medium", "bold"] as const;
export type FontWeight = (typeof FONT_WEIGHTS)[number];

export const SUBTITLE_POSITION_MODES = ["anchor", "free"] as const;
export type SubtitlePositionMode = (typeof SUBTITLE_POSITION_MODES)[number];

export const SUBTITLE_WRAP_MODES = ["chars", "sentence", "word"] as const;
export type SubtitleWrapMode = (typeof SUBTITLE_WRAP_MODES)[number];

export interface SubtitleStyleConfig {
  anchor: SubtitleAnchor;
  offset_px: number;
  position_mode: SubtitlePositionMode;
  free_x_pct: number;
  free_y_pct: number;
  clamp_to_safe_zone: boolean;
  max_lines: number;
  wrap_mode: SubtitleWrapMode;
  max_chars_per_line: number;
  font: string;
  size: number;
  weight: FontWeight;
  italic: boolean;
  primary_color: string;
  text_opacity: number;
  outline_width: number;
  outline_color: string;
  shadow_width: number;
  shadow_color: string;
  shadow_opacity: number;
  background: boolean;
  background_color: string;
  background_opacity: number;
  background_padding: number;
}

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyleConfig = {
  anchor: "bottom",
  offset_px: 200,
  position_mode: "anchor",
  free_x_pct: 50,
  free_y_pct: 85,
  clamp_to_safe_zone: true,
  max_lines: 2,
  wrap_mode: "chars",
  max_chars_per_line: 30,
  font: "Arial",
  size: 64,
  weight: "bold",
  italic: false,
  primary_color: "#FFFFFF",
  text_opacity: 100,
  outline_width: 3,
  outline_color: "#000000",
  shadow_width: 1,
  shadow_color: "#000000",
  shadow_opacity: 100,
  background: false,
  background_color: "#000000",
  background_opacity: 40,
  background_padding: 8,
};

export interface SubtitleStylePreset {
  id: number;
  name: string;
  style: SubtitleStyleConfig;
  is_builtin: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface FontListResponse {
  fonts: string[];
  scanned_at: string | null;
  source: "system" | "fallback";
}

export const subtitleApi = {
  listFonts: () => request<FontListResponse>("/api/v1/settings/fonts"),
  refreshFonts: () =>
    request<FontListResponse>("/api/v1/settings/fonts/refresh", {
      method: "POST",
    }),
  listSubtitlePresets: () =>
    request<SubtitleStylePreset[]>("/api/v1/settings/subtitle_presets"),
  getSubtitlePreset: (id: number) =>
    request<SubtitleStylePreset>(`/api/v1/settings/subtitle_presets/${id}`),
  createSubtitlePreset: (payload: {
    name: string;
    style: SubtitleStyleConfig;
    is_default?: boolean;
  }) =>
    request<SubtitleStylePreset>("/api/v1/settings/subtitle_presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateSubtitlePreset: (
    id: number,
    payload: {
      name?: string;
      style?: SubtitleStyleConfig;
      is_default?: boolean;
    },
  ) =>
    request<SubtitleStylePreset>(`/api/v1/settings/subtitle_presets/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteSubtitlePreset: (id: number) =>
    request<void>(`/api/v1/settings/subtitle_presets/${id}`, {
      method: "DELETE",
    }),
};
