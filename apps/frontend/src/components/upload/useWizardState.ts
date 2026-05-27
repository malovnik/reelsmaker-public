
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type AutoAnalyzeResponse,
  type ComposerStrategy,
  type FitMode,
  type ModelsInfo,
  type PostProductionOverrides,
  type PostProductionPreset,
  type SourceLanguage,
  type SubtitleStylePreset,
  type VisionProfile,
} from "@/lib/api";
import { extractVideoThumbnail } from "@/lib/video-thumbnail";
import { useJobSse, type UseJobSseResult } from "@/lib/sse";

export const ASPECTS = ["9:16", "1:1", "4:5", "16:9"] as const;
export type Aspect = (typeof ASPECTS)[number];

export const REEL_COUNT_MIN = 3;
export const REEL_COUNT_MAX = 225;

export interface UseWizardStateOptions {
  models: ModelsInfo;
  subtitlePresets: SubtitleStylePreset[];
  postProductionPresets: PostProductionPreset[];
  defaultUseSourceForRender: boolean;
  onJobCreated?: (jobId: string) => void;
}

export interface WizardState {
  file: File | null;
  sourceThumbnailDataUrl: string | null;
  uploading: boolean;
  jobId: string | null;
  error: string | null;
  pipelineMode: "auto" | "manual";
  autoAnalyzing: boolean;
  autoAnalysis: AutoAnalyzeResponse | null;
  composerStrategy: ComposerStrategy;
  provider: string;
  llmModel: string;
  transcriber: string;
  aspect: Aspect;
  fitMode: FitMode;
  sourceLang: SourceLanguage;
  visionProfile: VisionProfile;
  forceReingest: boolean;
  subtitlePresetId: number | null;
  postProductionPresetId: number | null;
  useProxy: boolean;
  useSourceForRender: boolean;
  reelCountMode: "auto" | "custom";
  reelCount: number;
  customSystemPrompt: string;
  splitScreenOverride: boolean | null;
  overrides: PostProductionOverrides;
  selectedSubtitlePreset: SubtitleStylePreset | null;
  selectedPostProductionPreset: PostProductionPreset | null;
  sse: UseJobSseResult;
}

export interface WizardActions {
  applySelectedFile: (picked: File) => void;
  clearSelectedFile: () => void;
  setError: (message: string | null) => void;
  setPipelineMode: (m: "auto" | "manual") => void;
  setComposerStrategy: (s: ComposerStrategy) => void;
  setProvider: (p: string) => void;
  setLlmModel: (m: string) => void;
  setTranscriber: (t: string) => void;
  setAspect: (a: Aspect) => void;
  setFitMode: (f: FitMode) => void;
  setSourceLang: (l: SourceLanguage) => void;
  setVisionProfile: (v: VisionProfile) => void;
  setForceReingest: (v: boolean) => void;
  setSubtitlePresetId: (id: number | null) => void;
  setPostProductionPresetId: (id: number | null) => void;
  setUseProxy: (v: boolean) => void;
  setUseSourceForRender: (v: boolean) => void;
  setReelCountMode: (m: "auto" | "custom") => void;
  setReelCount: (n: number) => void;
  setCustomSystemPrompt: (s: string) => void;
  setSplitScreenOverride: (v: boolean | null) => void;
  setOverride: (key: keyof PostProductionOverrides, enabled: boolean) => void;
  submit: () => Promise<void>;
  acceptAutoConfig: () => Promise<void>;
  switchToManual: () => void;
}

export function useWizardState(
  options: UseWizardStateOptions,
): { state: WizardState; actions: WizardActions } {
  const {
    models,
    subtitlePresets,
    postProductionPresets,
    defaultUseSourceForRender,
    onJobCreated,
  } = options;

  const [file, setFile] = useState<File | null>(null);
  const [sourceThumbnailDataUrl, setSourceThumbnailDataUrl] = useState<
    string | null
  >(null);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pipelineMode, setPipelineMode] = useState<"auto" | "manual">("auto");
  const [autoAnalyzing, setAutoAnalyzing] = useState(false);
  const [autoAnalysis, setAutoAnalysis] = useState<AutoAnalyzeResponse | null>(
    null,
  );
  const [composerStrategy, setComposerStrategy] =
    useState<ComposerStrategy>("auto");

  const defaultProvider = models.available_providers[0] ?? "gemini";
  const defaultModel =
    models.defaults[defaultProvider] ??
    models.defaults["gemini"] ??
    "gemini-3.1-flash-lite-preview";
  const defaultTranscriber = models.available_transcribers[0] ?? "mlx_whisper";

  const [provider, setProvider] = useState<string>(defaultProvider);
  const [llmModel, setLlmModel] = useState<string>(defaultModel);
  const [transcriber, setTranscriber] = useState<string>(defaultTranscriber);
  const [aspect, setAspect] = useState<Aspect>("9:16");
  const [fitMode, setFitMode] = useState<FitMode>("fill");
  const [sourceLang, setSourceLang] = useState<SourceLanguage>("auto");
  const [visionProfile, setVisionProfile] =
    useState<VisionProfile>("talking_head");
  const [forceReingest, setForceReingest] = useState<boolean>(false);

  const defaultSubtitlePresetId =
    subtitlePresets.find((p) => p.is_default)?.id ??
    subtitlePresets[0]?.id ??
    null;
  const [subtitlePresetId, setSubtitlePresetId] = useState<number | null>(
    defaultSubtitlePresetId,
  );
  const defaultPostProductionPresetId =
    postProductionPresets.find((p) => p.is_default)?.id ?? null;
  const [postProductionPresetId, setPostProductionPresetId] = useState<
    number | null
  >(defaultPostProductionPresetId);

  const [useProxy, setUseProxy] = useState<boolean>(true);
  const [useSourceForRender, setUseSourceForRender] = useState<boolean>(
    defaultUseSourceForRender,
  );
  const [reelCountMode, setReelCountMode] = useState<"auto" | "custom">("auto");
  const [reelCount, setReelCount] = useState<number>(12);

  const [customSystemPrompt, setCustomSystemPrompt] = useState<string>("");
  const [splitScreenOverride, setSplitScreenOverride] = useState<
    boolean | null
  >(null);

  const [overrides, setOverrides] = useState<PostProductionOverrides>({});
  const setOverride = useCallback(
    (key: keyof PostProductionOverrides, enabled: boolean) => {
      setOverrides((prev) => {
        const next = { ...prev };
        if (enabled) delete next[key];
        else next[key] = false;
        return next;
      });
    },
    [],
  );

  const selectedSubtitlePreset = useMemo(
    () =>
      subtitlePresetId !== null
        ? subtitlePresets.find((p) => p.id === subtitlePresetId) ?? null
        : null,
    [subtitlePresets, subtitlePresetId],
  );
  const selectedPostProductionPreset = useMemo(
    () =>
      postProductionPresetId !== null
        ? postProductionPresets.find((p) => p.id === postProductionPresetId) ??
          null
        : null,
    [postProductionPresets, postProductionPresetId],
  );

  const sse = useJobSse(jobId);

  useEffect(() => {
    if (sse.finalStatus === "done" && jobId && onJobCreated) {
      onJobCreated(jobId);
    }
  }, [sse.finalStatus, jobId, onJobCreated]);

  const applySelectedFile = useCallback((picked: File) => {
    setFile(picked);
    setSourceThumbnailDataUrl(null);
    extractVideoThumbnail(picked, 0.5)
      .then((dataUrl) => {
        setSourceThumbnailDataUrl(dataUrl);
      })
      .catch(() => {
        setSourceThumbnailDataUrl(null);
      });
  }, []);

  const clearSelectedFile = useCallback(() => {
    setFile(null);
    setSourceThumbnailDataUrl(null);
  }, []);

  const providerWithModelReset = useCallback(
    (v: string) => {
      setProvider(v);
      const next = models.defaults[v];
      if (next) setLlmModel(next);
    },
    [models.defaults],
  );

  const submit = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("transcriber", transcriber);
    form.append("llm_provider", provider);
    form.append("llm_model", llmModel);
    form.append("target_aspect", aspect);
    form.append("fit_mode", fitMode);
    form.append("source_language", sourceLang);
    if (subtitlePresetId !== null) {
      form.append("subtitle_style_preset_id", String(subtitlePresetId));
    }
    if (postProductionPresetId !== null) {
      form.append(
        "post_production_preset_id",
        String(postProductionPresetId),
      );
      if (Object.keys(overrides).length > 0) {
        form.append(
          "post_production_overrides_json",
          JSON.stringify(overrides),
        );
      }
    }
    form.append("use_proxy", String(useProxy));
    form.append("use_source_for_render", String(useSourceForRender));
    form.append("vision_profile", visionProfile);
    form.append("force_reingest", String(forceReingest));
    if (reelCountMode === "custom") {
      form.append("target_reel_count", String(reelCount));
    }
    // T9 — composer strategy override: передаём только если не "auto".
    if (composerStrategy !== "auto") {
      form.append("composer_strategy_override", composerStrategy);
    }
    // Task 3: опциональный доп-промпт → приклеивается к system-prompt
    // всех LLM-стадий этого job'а. Отправляем только если непусто
    // (бэк нормализует ещё раз).
    const trimmedPrompt = customSystemPrompt.trim();
    if (trimmedPrompt.length > 0) {
      form.append("custom_system_prompt", trimmedPrompt);
    }
    // Split-screen per-job override. null — использовать значение из пресета;
    // true/false — переопределить. Бэк игнорирует если пресет без companion.
    if (splitScreenOverride !== null) {
      form.append("split_screen_enabled", String(splitScreenOverride));
    }
    try {
      const job = await api.createJob(form);
      setJobId(job.id);
      // T11 Auto Mode: после создания запрашиваем /auto-analyze. Когда
      // вернётся — показываем AutoConfigSummary card (внизу wizard'а).
      // User принимает → PATCH /auto-config + pipeline запускается в
      // automatic режиме.
      if (pipelineMode === "auto") {
        setAutoAnalyzing(true);
        try {
          const analysis = await api.autoAnalyzeJob(job.id);
          setAutoAnalysis(analysis);
        } catch (autoErr) {
          console.error("auto-analyze failed", autoErr);
        } finally {
          setAutoAnalyzing(false);
        }
      } else if (onJobCreated) {
        onJobCreated(job.id);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Ошибка ${err.status}: ${JSON.stringify(err.detail)}`);
      } else {
        setError(String(err));
      }
    } finally {
      setUploading(false);
    }
  }, [
    file,
    transcriber,
    provider,
    llmModel,
    aspect,
    fitMode,
    sourceLang,
    subtitlePresetId,
    postProductionPresetId,
    overrides,
    useProxy,
    useSourceForRender,
    reelCountMode,
    reelCount,
    visionProfile,
    forceReingest,
    onJobCreated,
    pipelineMode,
    composerStrategy,
    customSystemPrompt,
    splitScreenOverride,
  ]);

  const acceptAutoConfig = useCallback(async () => {
    if (!jobId || !autoAnalysis) return;
    try {
      await fetch(`/api/v1/jobs/${jobId}/auto-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pacing_profile: autoAnalysis.pacing_profile,
          snap_strategy: autoAnalysis.snap_strategy,
          pause_compression_enabled: autoAnalysis.pause_compression_enabled,
          pause_compression_threshold_sec:
            autoAnalysis.pause_compression_threshold_sec,
          pause_compression_keep_sec: autoAnalysis.pause_compression_keep_sec,
          breath_compression_enabled: autoAnalysis.breath_compression_enabled,
          filler_words_removal_enabled:
            autoAnalysis.filler_words_removal_enabled,
          punchline_pause_enabled: autoAnalysis.punchline_pause_enabled,
          punchline_hold_after_sec: autoAnalysis.punchline_hold_after_sec,
          punch_in_zoom_enabled: autoAnalysis.punch_in_zoom_enabled,
          punch_in_zoom_scale: autoAnalysis.punch_in_zoom_scale,
          punch_in_zoom_probability: autoAnalysis.punch_in_zoom_probability,
          ken_burns_drift_enabled: autoAnalysis.ken_burns_drift_enabled,
          ken_burns_scale_per_sec: autoAnalysis.ken_burns_scale_per_sec,
          coherence_threshold: autoAnalysis.coherence_threshold,
          rhythm_aware_cuts_enabled: autoAnalysis.rhythm_aware_cuts_enabled,
        }),
      });
      if (onJobCreated) onJobCreated(jobId);
    } catch (err) {
      setError(`Не удалось применить AutoConfig: ${String(err)}`);
    }
  }, [jobId, autoAnalysis, onJobCreated]);

  const switchToManual = useCallback(() => {
    setAutoAnalysis(null);
    setPipelineMode("manual");
    if (jobId && onJobCreated) onJobCreated(jobId);
  }, [jobId, onJobCreated]);

  const state: WizardState = {
    file,
    sourceThumbnailDataUrl,
    uploading,
    jobId,
    error,
    pipelineMode,
    autoAnalyzing,
    autoAnalysis,
    composerStrategy,
    provider,
    llmModel,
    transcriber,
    aspect,
    fitMode,
    sourceLang,
    visionProfile,
    forceReingest,
    subtitlePresetId,
    postProductionPresetId,
    useProxy,
    useSourceForRender,
    reelCountMode,
    reelCount,
    customSystemPrompt,
    splitScreenOverride,
    overrides,
    selectedSubtitlePreset,
    selectedPostProductionPreset,
    sse,
  };

  const actions: WizardActions = {
    applySelectedFile,
    clearSelectedFile,
    setError,
    setPipelineMode,
    setComposerStrategy,
    setProvider: providerWithModelReset,
    setLlmModel,
    setTranscriber,
    setAspect,
    setFitMode,
    setSourceLang,
    setVisionProfile,
    setForceReingest,
    setSubtitlePresetId,
    setPostProductionPresetId,
    setUseProxy,
    setUseSourceForRender,
    setReelCountMode,
    setReelCount,
    setCustomSystemPrompt,
    setSplitScreenOverride,
    setOverride,
    submit,
    acceptAutoConfig,
    switchToManual,
  };

  return { state, actions };
}
