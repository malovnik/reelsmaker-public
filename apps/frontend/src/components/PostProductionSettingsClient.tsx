
import { useCallback, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  DEFAULT_POST_PRODUCTION_CONFIG,
  DEFAULT_SPLIT_SCREEN,
  type PostProductionConfig,
  type PostProductionPreset,
  type SplitScreenConfig,
  type VideoAsset,
} from "@/lib/api";
import {
  extractVideoThumbnail,
  readImageFileAsDataUrl,
} from "@/lib/video-thumbnail";
import {
  AssetsColumn,
  AudioNormalizationSection,
  extractDetail,
  IntroOutroSection,
  PresetIdentitySection,
  PresetListColumn,
  SplitScreenSection,
  VideoEffectsSection,
  ZoomSection,
} from "@/components/settings/post-production";

interface Props {
  initialAssets: VideoAsset[];
  initialPresets: PostProductionPreset[];
}

interface DraftPreset {
  id: number | null;
  name: string;
  is_default: boolean;
  intro_asset_id: number | null;
  outro_asset_id: number | null;
  companion_asset_id: number | null;
  config: PostProductionConfig;
}

const EMPTY_DRAFT: DraftPreset = {
  id: null,
  name: "",
  is_default: false,
  intro_asset_id: null,
  outro_asset_id: null,
  companion_asset_id: null,
  config: { ...DEFAULT_POST_PRODUCTION_CONFIG },
};

function presetToDraft(preset: PostProductionPreset): DraftPreset {
  return {
    id: preset.id,
    name: preset.name,
    is_default: preset.is_default,
    intro_asset_id: preset.intro_asset_id,
    outro_asset_id: preset.outro_asset_id,
    companion_asset_id: preset.companion_asset_id,
    config: {
      ...preset.config,
      split_screen: preset.config.split_screen ?? { ...DEFAULT_SPLIT_SCREEN },
    },
  };
}

export function PostProductionSettingsClient({
  initialAssets,
  initialPresets,
}: Props) {
  const [assets, setAssets] = useState<VideoAsset[]>(initialAssets);
  const [presets, setPresets] =
    useState<PostProductionPreset[]>(initialPresets);
  const [selectedPresetId, setSelectedPresetId] = useState<
    number | "new" | null
  >(initialPresets[0]?.id ?? null);
  const [draft, setDraft] = useState<DraftPreset>(
    initialPresets[0] ? presetToDraft(initialPresets[0]) : { ...EMPTY_DRAFT },
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadingAsset, setUploadingAsset] = useState(false);

  const assetUploadRef = useRef<HTMLInputElement>(null);
  const [assetName, setAssetName] = useState("");

  const sampleFrameInputRef = useRef<HTMLInputElement>(null);
  const [sampleFrameDataUrl, setSampleFrameDataUrl] = useState<string | null>(
    null,
  );
  const [sampleFrameLoading, setSampleFrameLoading] = useState(false);

  const onSampleFrameSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const picked = event.target.files?.[0];
      if (!picked) return;
      setSampleFrameLoading(true);
      try {
        let dataUrl: string | null = null;
        if (picked.type.startsWith("image/")) {
          dataUrl = await readImageFileAsDataUrl(picked);
        } else if (picked.type.startsWith("video/")) {
          dataUrl = await extractVideoThumbnail(picked, 0.5);
        }
        setSampleFrameDataUrl(dataUrl);
      } finally {
        setSampleFrameLoading(false);
        if (sampleFrameInputRef.current) {
          sampleFrameInputRef.current.value = "";
        }
      }
    },
    [],
  );

  const resetSampleFrame = useCallback(() => {
    setSampleFrameDataUrl(null);
    if (sampleFrameInputRef.current) {
      sampleFrameInputRef.current.value = "";
    }
  }, []);

  const refreshAssets = useCallback(async () => {
    try {
      setAssets(await api.listAssets());
    } catch (err) {
      setError(
        err instanceof Error
          ? `Не удалось загрузить ассеты: ${err.message}`
          : "Не удалось загрузить ассеты",
      );
    }
  }, []);

  const refreshPresets = useCallback(async () => {
    try {
      setPresets(await api.listPostProductionPresets());
    } catch (err) {
      setError(
        err instanceof Error
          ? `Не удалось загрузить пресеты: ${err.message}`
          : "Не удалось загрузить пресеты",
      );
    }
  }, []);

  const selectPreset = useCallback(
    (id: number | "new" | null) => {
      setSelectedPresetId(id);
      setError(null);
      if (id === "new" || id === null) {
        setDraft({ ...EMPTY_DRAFT });
      } else {
        const found = presets.find((p) => p.id === id);
        setDraft(found ? presetToDraft(found) : { ...EMPTY_DRAFT });
      }
    },
    [presets],
  );

  const onUploadAsset = useCallback(async () => {
    const file = assetUploadRef.current?.files?.[0];
    if (!file) {
      setError("Сначала выбери файл");
      return;
    }
    if (!assetName.trim()) {
      setError("Введи название — без него ролик не сохранится");
      return;
    }
    setUploadingAsset(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", assetName.trim());
      const result = await api.importAsset(form);
      await refreshAssets();
      setAssetName("");
      if (assetUploadRef.current) assetUploadRef.current.value = "";
      if (!result.created) {
        setError(`Файл уже был загружен ранее как «${result.asset.name}»`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? extractDetail(err) : String(err));
    } finally {
      setUploadingAsset(false);
    }
  }, [assetName, refreshAssets]);

  const onDeleteAsset = useCallback(
    async (id: number) => {
      if (!confirm("Удалить ролик? Файл будет стёрт с диска.")) return;
      try {
        await api.deleteAsset(id);
        await refreshAssets();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setError(
            "Этот ролик используется в одном или нескольких пресетах — удали его из них сначала",
          );
        } else {
          setError(err instanceof ApiError ? extractDetail(err) : String(err));
        }
      }
    },
    [refreshAssets],
  );

  const onSavePreset = useCallback(async () => {
    if (!draft.name.trim()) {
      setError("Введи название — без него пресет не сохранится");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (draft.id === null) {
        const created = await api.createPostProductionPreset({
          name: draft.name,
          is_default: draft.is_default,
          intro_asset_id: draft.intro_asset_id,
          outro_asset_id: draft.outro_asset_id,
          companion_asset_id: draft.companion_asset_id,
          config: draft.config,
        });
        await refreshPresets();
        setSelectedPresetId(created.id);
        setDraft(presetToDraft(created));
      } else {
        const updated = await api.updatePostProductionPreset(draft.id, {
          name: draft.name,
          is_default: draft.is_default,
          intro_asset_id: draft.intro_asset_id,
          outro_asset_id: draft.outro_asset_id,
          companion_asset_id: draft.companion_asset_id,
          config: draft.config,
        });
        await refreshPresets();
        setDraft(presetToDraft(updated));
      }
    } catch (err) {
      setError(err instanceof ApiError ? extractDetail(err) : String(err));
    } finally {
      setBusy(false);
    }
  }, [draft, refreshPresets]);

  const onDeletePreset = useCallback(async () => {
    if (draft.id === null) return;
    if (!confirm(`Удалить пресет «${draft.name}»?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deletePostProductionPreset(draft.id);
      await refreshPresets();
      setSelectedPresetId(null);
      setDraft({ ...EMPTY_DRAFT });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          "Этот пресет сейчас используется в обработке — дождись завершения нарезки",
        );
      } else {
        setError(err instanceof ApiError ? extractDetail(err) : String(err));
      }
    } finally {
      setBusy(false);
    }
  }, [draft, refreshPresets]);

  const updateConfig = useCallback(
    <K extends keyof PostProductionConfig>(
      key: K,
      value: PostProductionConfig[K],
    ) => {
      setDraft((d) => ({ ...d, config: { ...d.config, [key]: value } }));
    },
    [],
  );

  const updateSplitScreen = useCallback((next: SplitScreenConfig) => {
    setDraft((d) => ({
      ...d,
      config: { ...d.config, split_screen: next },
    }));
  }, []);

  const updateSplitScreenField = useCallback(
    <K extends keyof SplitScreenConfig>(key: K, value: SplitScreenConfig[K]) => {
      setDraft((d) => ({
        ...d,
        config: {
          ...d.config,
          split_screen: { ...d.config.split_screen, [key]: value },
        },
      }));
    },
    [],
  );

  const sortedPresets = useMemo(
    () =>
      [...presets].sort((a, b) => {
        if (a.is_default !== b.is_default) return a.is_default ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [presets],
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
      {/* Левая колонка: ролики + пресеты в одной вертикальной полосе */}
      <div className="flex flex-col gap-6">
        <AssetsColumn
          assets={assets}
          assetUploadRef={assetUploadRef}
          assetName={assetName}
          onAssetNameChange={setAssetName}
          onUploadAsset={onUploadAsset}
          uploadingAsset={uploadingAsset}
          onDeleteAsset={onDeleteAsset}
        />
        <PresetListColumn
          presets={sortedPresets}
          selectedPresetId={selectedPresetId}
          onSelect={selectPreset}
        />
      </div>

      <section className="surface-card flex flex-col gap-4 p-5">
        {selectedPresetId === null ? (
          <div className="flex h-full items-center justify-center text-sm text-[color:var(--text-muted)]">
            Выбери пресет слева или создай новый
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">
                {draft.id === null ? "Новый пресет" : `Пресет #${draft.id}`}
              </h2>
              <div className="flex gap-2">
                {draft.id !== null && (
                  <button
                    onClick={onDeletePreset}
                    disabled={busy}
                    type="button"
                    className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--danger)] hover:text-[color:var(--danger)] disabled:opacity-40"
                  >
                    Удалить
                  </button>
                )}
                <button
                  onClick={onSavePreset}
                  disabled={busy}
                  type="button"
                  className="rounded-lg bg-[color:var(--accent-primary)] px-3 py-1 text-xs font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:opacity-40"
                >
                  {busy ? "…" : draft.id === null ? "Создать" : "Сохранить"}
                </button>
              </div>
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 p-3 text-xs text-[color:var(--danger)]"
              >
                {error}
              </div>
            )}

            <PresetIdentitySection
              name={draft.name}
              isDefault={draft.is_default}
              onNameChange={(value) =>
                setDraft((d) => ({ ...d, name: value }))
              }
              onIsDefaultChange={(value) =>
                setDraft((d) => ({ ...d, is_default: value }))
              }
            />

            <IntroOutroSection
              assets={assets}
              introAssetId={draft.intro_asset_id}
              outroAssetId={draft.outro_asset_id}
              onIntroChange={(id) =>
                setDraft((d) => ({ ...d, intro_asset_id: id }))
              }
              onOutroChange={(id) =>
                setDraft((d) => ({ ...d, outro_asset_id: id }))
              }
            />

            <AudioNormalizationSection
              config={draft.config}
              onConfigChange={updateConfig}
            />

            <ZoomSection config={draft.config} onConfigChange={updateConfig} />

            <VideoEffectsSection
              config={draft.config}
              onConfigChange={updateConfig}
            />

            <SplitScreenSection
              config={draft.config}
              assets={assets}
              companionAssetId={draft.companion_asset_id}
              onCompanionAssetChange={(id) =>
                setDraft((d) => ({ ...d, companion_asset_id: id }))
              }
              onSplitScreenChange={updateSplitScreen}
              onSplitScreenFieldChange={updateSplitScreenField}
              sampleFrameDataUrl={sampleFrameDataUrl}
              sampleFrameLoading={sampleFrameLoading}
              sampleFrameInputRef={sampleFrameInputRef}
              onSampleFrameSelected={onSampleFrameSelected}
              onResetSampleFrame={resetSampleFrame}
            />
          </>
        )}
      </section>
    </div>
  );
}
