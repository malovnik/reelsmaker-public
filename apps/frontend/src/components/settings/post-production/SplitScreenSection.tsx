
import type { ChangeEvent, RefObject } from "react";
import {
  SPLIT_SCREEN_PANEL_FIT_MODES,
  type PostProductionConfig,
  type SplitScreenConfig,
  type SplitScreenPanelFitMode,
  type VideoAsset,
} from "@/lib/api";
import { SplitScreenPreviewEditor } from "@/components/SplitScreenPreviewEditor";
import { resolveHint } from "@/components/settings-shared";
import { AssetSelect, Field, Section, Toggle } from "./shared";

const splitHint = resolveHint({ hintKey: "split_screen_enabled" });

interface Props {
  config: PostProductionConfig;
  assets: VideoAsset[];
  companionAssetId: number | null;
  onCompanionAssetChange: (id: number | null) => void;
  onSplitScreenChange: (next: SplitScreenConfig) => void;
  onSplitScreenFieldChange: <K extends keyof SplitScreenConfig>(
    key: K,
    value: SplitScreenConfig[K],
  ) => void;
  sampleFrameDataUrl: string | null;
  sampleFrameLoading: boolean;
  sampleFrameInputRef: RefObject<HTMLInputElement | null>;
  onSampleFrameSelected: (event: ChangeEvent<HTMLInputElement>) => void;
  onResetSampleFrame: () => void;
}

const FIT_LABELS: Record<SplitScreenPanelFitMode, string> = {
  fill: "Crop-to-fill",
  fit: "Fit (рамки)",
  manual: "Вручную",
};

export function SplitScreenSection({
  config,
  assets,
  companionAssetId,
  onCompanionAssetChange,
  onSplitScreenChange,
  onSplitScreenFieldChange,
  sampleFrameDataUrl,
  sampleFrameLoading,
  sampleFrameInputRef,
  onSampleFrameSelected,
  onResetSampleFrame,
}: Props) {
  const splitScreen = config.split_screen;

  const renderFitButtons = (
    field: "main_fit_mode" | "companion_fit_mode",
    current: SplitScreenPanelFitMode,
  ) => (
    <div className="flex gap-1">
      {SPLIT_SCREEN_PANEL_FIT_MODES.map((m) => {
        const active = current === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => onSplitScreenFieldChange(field, m)}
            className={`flex-1 rounded-none border px-2 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "border-[color:var(--gold)] bg-[color:var(--gold)] text-[color:var(--gold-dim)]"
                : "border-[color:var(--line)] bg-[color:var(--ink)] text-[color:var(--mute-2)] hover:border-[color:var(--line)] hover:text-[color:var(--paper)]"
            }`}
          >
            {FIT_LABELS[m]}
          </button>
        );
      })}
    </div>
  );

  const mainManual = splitScreen.main_fit_mode === "manual";
  const companionManual = splitScreen.companion_fit_mode === "manual";
  const ratioDisabled = mainManual && companionManual;

  return (
    <Section
      title="Сплит-скрин"
      aside={
        <span className="inline-flex items-center gap-1.5">
          {splitHint.badgeNode}
          {splitHint.adornment}
        </span>
      }
    >
      <Field label="Компаньон-ролик">
        <AssetSelect
          assets={assets}
          value={companionAssetId}
          onChange={onCompanionAssetChange}
        />
      </Field>
      <p className="text-[11px] text-[color:var(--mute)]">
        Второй видеопоток, который накладывается поверх основного.
        Например, реакция на экран или дополнительная камера.
      </p>

      <Toggle
        label="Включить сплит-скрин"
        checked={splitScreen.enabled}
        onChange={(v) => onSplitScreenFieldChange("enabled", v)}
      />

      {splitScreen.enabled && (
        <>
          <div className="rounded-none border border-[color:var(--warning)]/40/30 bg-amber-950/20 p-3 text-sm text-[color:var(--warning)]">
            <div className="mb-1 font-medium">Split-режим активен</div>
            <div className="leading-relaxed">
              Основные настройки <span className="font-mono">fit / fill</span>{" "}
              из глобальных не применяются к split-рилсам — кропом управляют{" "}
              <span className="font-mono">Main Panel Transform</span> и{" "}
              <span className="font-mono">Companion Panel Transform</span>{" "}
              ниже. Превью в этом разделе 1:1 соответствует финальному рендеру.
            </div>
          </div>
          <Field label="Как кадрировать основу (main)">
            {renderFitButtons("main_fit_mode", splitScreen.main_fit_mode)}
          </Field>
          <Field label="Как кадрировать компаньон (companion)">
            {renderFitButtons(
              "companion_fit_mode",
              splitScreen.companion_fit_mode,
            )}
          </Field>

          <Field label={`Соотношение разделения: ${splitScreen.split_ratio}%`}>
            <input
              type="range"
              min={20}
              max={80}
              step={1}
              value={splitScreen.split_ratio}
              disabled={ratioDisabled}
              onChange={(e) =>
                onSplitScreenFieldChange("split_ratio", Number(e.target.value))
              }
              className="w-full accent-[color:var(--gold)] disabled:opacity-40"
            />
            <span className="text-[11px] text-[color:var(--mute)]">
              {ratioDisabled
                ? "Обе панели в режиме «Вручную» — соотношение игнорируется, позиции задаются перетаскиванием."
                : "Панель в режиме Fill/Fit занимает долю кадра по соотношению. Main — сверху, companion — снизу."}
            </span>
          </Field>

          {companionAssetId !== null ? (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5 rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] p-3">
                <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--mute)]">
                  Образец кадра для предпросмотра (опционально)
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    ref={sampleFrameInputRef}
                    type="file"
                    accept="image/*,video/*"
                    onChange={onSampleFrameSelected}
                    className="block max-w-full text-[11px] text-[color:var(--paper)] file:mr-2 file:rounded-none file:border file:border-[color:var(--line)] file:bg-[color:var(--ink)] file:px-2 file:py-1 file:text-[11px] file:text-[color:var(--paper)] hover:file:bg-[color:var(--ink-3)]"
                  />
                  {sampleFrameDataUrl && (
                    <button
                      type="button"
                      onClick={onResetSampleFrame}
                      className="rounded-none border border-[color:var(--line)] bg-[color:var(--ink)] px-2 py-1 text-[11px] text-[color:var(--paper)] hover:bg-[color:var(--ink-3)]"
                    >
                      Сбросить
                    </button>
                  )}
                  {sampleFrameLoading && (
                    <span className="text-[11px] text-[color:var(--mute)]">
                      Извлекаю кадр…
                    </span>
                  )}
                </div>
                <span className="text-[11px] leading-relaxed text-[color:var(--mute)]">
                  Изображение или видео используется только для
                  настройки preview в этой сессии — в базу ничего
                  не сохраняется.
                </span>
              </div>
              <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--mute)]">
                Превью раскладки
              </span>
              <div className="overflow-x-auto">
                <SplitScreenPreviewEditor
                  config={splitScreen}
                  sourceThumbUrl={sampleFrameDataUrl}
                  companionThumbUrl={`/api/v1/post_production/assets/${companionAssetId}/thumbnail?time_sec=0.5`}
                  previewHeight={300}
                  onChange={onSplitScreenChange}
                />
              </div>
            </div>
          ) : (
            <p className="rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] px-3 py-2 text-[11px] text-[color:var(--mute)]">
              Выбери компаньон-ролик выше, чтобы увидеть превью
              раскладки.
            </p>
          )}
        </>
      )}
    </Section>
  );
}
