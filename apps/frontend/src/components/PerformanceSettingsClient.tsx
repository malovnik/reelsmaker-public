
import {
  useCallback,
  useMemo,
  useState,
  useTransition,
  type Dispatch,
  type SetStateAction,
} from "react";

import { ApiError, api, type PerformanceSettings } from "@/lib/api";
import {
  AdaptiveAudioGroup,
  AutoModeGroup,
  CoherenceGroup,
  CrossChunkGroup,
  CutSnapGroup,
  DefaultsGroup,
  EnsembleGroup,
  FillerRemovalGroup,
  JLCutGroup,
  LLMGroup,
  ManualEditingPresetCard,
  MotionGroup,
  MultiArcGroup,
  NarrativeModeGroup,
  PacingGroup,
  PauseCompressionGroup,
  PreferenceGroup,
  ProxyCacheGroup,
  ProxyGroup,
  ProxySkipGroup,
  PunchlineGroup,
  QualityGatesGroup,
  ReelCountGroup,
  RenderConcurrencyGroup,
  RhythmCutsGroup,
  SaveBar,
  SemanticChunkingGroup,
  type SaveStatus,
} from "@/components/settings/performance-groups";

const SAVED_AUTO_RESET_MS = 2000;

interface Props {
  initial: PerformanceSettings;
}

type StateUpdater = Dispatch<SetStateAction<PerformanceSettings>>;
type StatusUpdater = Dispatch<SetStateAction<SaveStatus>>;

export function PerformanceSettingsClient({ initial }: Props) {
  const [values, setValues] = useState<PerformanceSettings>(initial);
  const [savedSnapshot, setSavedSnapshot] =
    useState<PerformanceSettings>(initial);
  const [status, setStatus] = useState<SaveStatus>({ kind: "pristine" });
  const [isPending, startTransition] = useTransition();

  const isDirty = useMemo(
    () => !shallowEqual(values, savedSnapshot),
    [values, savedSnapshot],
  );

  const update = useCallback(
    <K extends keyof PerformanceSettings>(
      key: K,
      value: PerformanceSettings[K],
    ) => {
      setValues((prev) => ({ ...prev, [key]: value }));
      setStatus((prev) => (prev.kind === "saving" ? prev : { kind: "dirty" }));
    },
    [],
  );

  const handleReset = useCallback(() => {
    setValues(savedSnapshot);
    setStatus({ kind: "pristine" });
  }, [savedSnapshot]);

  const handleSave = useCallback(() => {
    if (!isDirty || status.kind === "saving") return;
    setStatus({ kind: "saving" });
    startTransition(async () => {
      try {
        const persisted = await api.updatePerformanceSettings(values);
        setSavedSnapshot(persisted);
        setValues(persisted);
        setStatus({ kind: "saved" });
        window.setTimeout(() => {
          setStatus((prev) =>
            prev.kind === "saved" ? { kind: "pristine" } : prev,
          );
        }, SAVED_AUTO_RESET_MS);
      } catch (exc) {
        const message =
          exc instanceof ApiError
            ? `${exc.status}: ${stringifyDetail(exc.detail)}`
            : (exc as Error).message;
        setStatus({ kind: "error", message });
      }
    });
  }, [isDirty, status.kind, values]);

  const applyManualPreset = useCallback(() => {
    applyManualEditingPreset(setValues, setStatus);
  }, []);

  const resetAutoMode = useCallback(() => {
    resetAutoModeGroup(setValues, setStatus);
  }, []);
  const resetPacing = useCallback(() => {
    resetPacingGroup(setValues, setStatus);
  }, []);
  const resetPunchline = useCallback(() => {
    resetPunchlineGroup(setValues, setStatus);
  }, []);
  const resetMotion = useCallback(() => {
    resetMotionGroup(setValues, setStatus);
  }, []);
  const resetReelCount = useCallback(() => {
    resetReelCountGroup(setValues, setStatus);
  }, []);
  const resetPreference = useCallback(() => {
    resetPreferenceGroup(setValues, setStatus);
  }, []);
  const resetAdaptiveAudio = useCallback(() => {
    resetAdaptiveAudioGroup(setValues, setStatus);
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <ManualEditingPresetCard onApply={applyManualPreset} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <LLMGroup values={values} update={update} />
        <NarrativeModeGroup values={values} update={update} />
        <MultiArcGroup values={values} update={update} />
        <RenderConcurrencyGroup values={values} update={update} />
        <DefaultsGroup values={values} update={update} />
        <CoherenceGroup values={values} update={update} />
        <QualityGatesGroup values={values} update={update} />
        <AutoModeGroup
          values={values}
          update={update}
          onReset={resetAutoMode}
        />
        <PacingGroup values={values} update={update} onReset={resetPacing} />
        <PunchlineGroup
          values={values}
          update={update}
          onReset={resetPunchline}
        />
        <MotionGroup values={values} update={update} onReset={resetMotion} />
        <ReelCountGroup
          values={values}
          update={update}
          onReset={resetReelCount}
        />
        <PreferenceGroup
          values={values}
          update={update}
          onReset={resetPreference}
        />
        <AdaptiveAudioGroup
          values={values}
          update={update}
          onReset={resetAdaptiveAudio}
        />
        {/* DORMANT: Screencast auto-zoom (T2.8) — detector/planner работают,
            но merge ZoomKeyframe в ProjectGraph.ZoomPlan требует расширения
            zoom_planner API и отложен на follow-up спринт. Тоже про deictic
            zoom. UI скрыт, чтобы не давать ложный контроль. Backend stubs
            (cursor_detector, spring_zoom_planner, deictic_zoom) сохранены
            для будущей реализации. Функция resetScreencastZoomGroup оставлена
            в коде — она сбрасывает persisted PerformanceSettings поля. */}
        <PauseCompressionGroup values={values} update={update} />
        <EnsembleGroup values={values} update={update} />
        <FillerRemovalGroup values={values} update={update} />
        <CutSnapGroup values={values} update={update} />
        <RhythmCutsGroup values={values} update={update} />
        <JLCutGroup values={values} update={update} />
        <SemanticChunkingGroup values={values} update={update} />
        <CrossChunkGroup values={values} update={update} />
        <ProxyGroup values={values} update={update} />
        <ProxyCacheGroup values={values} update={update} />
        <ProxySkipGroup values={values} update={update} />
      </div>

      <SaveBar
        status={status}
        isDirty={isDirty}
        isPending={isPending}
        onSave={handleSave}
        onReset={handleReset}
      />
    </div>
  );
}

function shallowEqual<T extends object>(a: T, b: T): boolean {
  for (const key of Object.keys(a) as (keyof T)[]) {
    if (a[key] !== b[key]) return false;
  }
  return true;
}

function stringifyDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail: unknown }).detail;
    return typeof inner === "string" ? inner : JSON.stringify(inner);
  }
  return "проверь, что сервер отвечает";
}

function markDirty(setStatus: StatusUpdater) {
  setStatus((prev) => (prev.kind === "saving" ? prev : { kind: "dirty" }));
}

function resetAutoModeGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    pipeline_mode: "automatic",
  }));
  markDirty(setStatus);
}

function resetPacingGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    pacing_profile: "balanced",
    snap_strategy: "onset",
    onset_snap_max_shift_sec: 0.08,
  }));
  markDirty(setStatus);
}

function resetPunchlineGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    punchline_pause_enabled: true,
    punchline_pitch_drop_hz: 20,
    punchline_hold_after_sec: 0.5,
  }));
  markDirty(setStatus);
}

function resetMotionGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    punch_in_zoom_enabled: true,
    punch_in_zoom_scale: 1.08,
    punch_in_zoom_probability: 0.3,
    punch_in_zoom_hold_ms: 600,
    ken_burns_drift_enabled: false,
    ken_burns_scale_per_sec: 0.002,
    ken_burns_max_scale: 1.025,
  }));
  markDirty(setStatus);
}

function resetReelCountGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    reel_count_enforce_floor_ceiling: true,
    reel_count_dedup_jaccard_threshold: 0.7,
  }));
  markDirty(setStatus);
}

function resetPreferenceGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    preference_retrieval_mode: "cosine",
  }));
  markDirty(setStatus);
}

function resetAdaptiveAudioGroup(setValues: StateUpdater, setStatus: StatusUpdater) {
  setValues((prev) => ({
    ...prev,
    mouth_sound_removal_enabled: false,
    breath_classifier_enabled: false,
    context_aware_keep_sec_enabled: true,
    smart_jl_chooser_enabled: false,
    adaptive_leveller_enabled: false,
  }));
  markDirty(setStatus);
}

// DORMANT: resetScreencastZoomGroup удалён вместе с UI-секцией Screencast
// auto-zoom. PerformanceSettings-поля (screencast_cursor_zoom_enabled,
// screencast_damping_profile, screencast_zoom_max_factor, deictic_zoom_enabled)
// сохранены для обратной совместимости persisted settings.

function applyManualEditingPreset(
  setValues: StateUpdater,
  setStatus: StatusUpdater,
) {
  setValues((prev) => ({
    ...prev,
    // mouth_sound_removal_enabled убран — feature dormant, UI скрыт.
    breath_classifier_enabled: true,
    context_aware_keep_sec_enabled: true,
    smart_jl_chooser_enabled: true,
    adaptive_leveller_enabled: true,
  }));
  markDirty(setStatus);
}
