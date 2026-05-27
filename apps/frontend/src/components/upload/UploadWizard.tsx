
import { Link } from "react-router-dom";
import { useCallback, useRef, useState } from "react";
import {
  FIT_MODES,
  SOURCE_LANGUAGES,
  type FitMode,
  type ModelsInfo,
  type PostProductionPreset,
  type ProfileMaskRead,
  type SourceLanguage,
  type SubtitleStylePreset,
} from "@/lib/api";
import { ProfileSelector } from "@/components/ProfileSelector";
import { SubtitlePreview } from "@/components/SubtitlePreview";
import { AutoConfigSummary } from "@/components/upload/AutoConfigSummary";
import { AspectPreview } from "@/components/upload/AspectPreview";
import { VideoPreviewCard } from "@/components/upload/VideoPreviewCard";
import { SplitScreenPreviewEditor } from "@/components/SplitScreenPreviewEditor";
import {
  ComposerStrategyBlock,
  Field,
  OverrideCheckbox,
  Select,
  Step,
  ToggleRow,
} from "./WizardSteps";
import {
  ASPECTS,
  REEL_COUNT_MAX,
  REEL_COUNT_MIN,
  useWizardState,
  type Aspect,
} from "./useWizardState";

const ACCEPTED = [".mp4", ".mov", ".mkv", ".webm", ".m4v"];

const ASPECT_LABEL: Record<Aspect, string> = {
  "9:16": "Вертикально",
  "1:1": "Квадрат",
  "4:5": "Портрет",
  "16:9": "Горизонталь",
};

const SOURCE_LANG_LABELS: Record<SourceLanguage, string> = {
  auto: "Определить автоматически",
  ru: "Русский",
  en: "English",
  de: "Deutsch",
  es: "Español",
  fr: "Français",
  it: "Italiano",
  pt: "Português",
  zh: "中文",
  ja: "日本語",
  ko: "한국어",
};

const FIT_MODE_LABEL: Record<FitMode, string> = {
  fill: "Заполнить кадр + центрировать лицо",
  fit: "Сохранить весь кадр (чёрные поля)",
};

const PROFILE_LABEL: Record<string, string> = {
  talking_head: "Говорящая голова",
  fashion: "Фэшн и стиль",
  travel: "Путешествия",
  screencast: "Скринкаст",
  custom: "Своя настройка",
};

function isAcceptedFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  const lower = file.name.toLowerCase();
  return ACCEPTED.some((ext) => lower.endsWith(ext));
}

interface Props {
  models: ModelsInfo;
  subtitlePresets?: SubtitleStylePreset[];
  postProductionPresets?: PostProductionPreset[];
  profileMasks?: ProfileMaskRead[];
  defaultUseSourceForRender?: boolean;
  onJobCreated?: (jobId: string) => void;
}

export function UploadWizard({
  models,
  subtitlePresets = [],
  postProductionPresets = [],
  profileMasks = [],
  defaultUseSourceForRender = false,
  onJobCreated,
}: Props) {
  const { state, actions } = useWizardState({
    models,
    subtitlePresets,
    postProductionPresets,
    defaultUseSourceForRender,
    onJobCreated,
  });

  const [isDragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragging(false);
      const dropped = event.dataTransfer.files[0];
      if (!dropped) return;
      if (!isAcceptedFile(dropped)) {
        actions.setError(
          `Поддерживаются только ${ACCEPTED.join(", ")}. Получен: ${dropped.name}`,
        );
        return;
      }
      actions.setError(null);
      actions.applySelectedFile(dropped);
    },
    [actions],
  );

  const onSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const selected = event.target.files?.[0];
      if (!selected) return;
      if (!isAcceptedFile(selected)) {
        actions.setError(
          `Поддерживаются только ${ACCEPTED.join(", ")}. Получен: ${selected.name}`,
        );
        return;
      }
      actions.setError(null);
      actions.applySelectedFile(selected);
    },
    [actions],
  );

  if (models.available_providers.length === 0) {
    return (
      <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-5 text-sm text-[color:var(--danger)]">
        Нужно задать ключ LLM-провайдера. Добавь <code>GEMINI_API_KEY</code>{" "}
        в файл <code>.env</code> и перезапусти сервер командой{" "}
        <code>./run.sh</code>.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Step
        index={1}
        title="Под какой тип видео нарезаем"
        hint="Если не уверен — выбери любой. После загрузки мы подскажем точный профиль."
      >
        <ProfileSelector
          value={state.visionProfile}
          onChange={actions.setVisionProfile}
          masks={profileMasks}
        />
      </Step>

      {state.projects.length > 0 && (
        <Field label="Проект (папка)">
          <select
            value={state.projectId ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              actions.setProjectId(raw === "" ? null : Number(raw));
            }}
            className="w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
          >
            <option value="">— без проекта —</option>
            {state.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-[color:var(--text-muted)]">
            Готовый джоб попадёт в выбранную папку проекта.
          </span>
        </Field>
      )}

      <Step index={2} title="Видео">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          onChange={onSelect}
          className="hidden"
        />
        {state.file ? (
          <VideoPreviewCard file={state.file} onRemove={actions.clearSelectedFile} />
        ) : (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            className={[
              "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors",
              isDragging
                ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary-subtle)]"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] hover:border-[color:var(--text-primary)]",
            ].join(" ")}
            role="button"
            tabIndex={0}
            aria-label="Область загрузки видео"
          >
            <svg
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mb-3 text-[color:var(--text-muted)]"
              aria-hidden="true"
            >
              <path d="M12 15V3m0 0l-4 4m4-4l4 4" />
              <path d="M20 15v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4" />
            </svg>
            <span className="text-sm font-medium text-[color:var(--text-primary)]">
              Перетащи видео или выбери файл
            </span>
            <span className="mt-2 text-xs text-[color:var(--text-muted)]">
              MP4, MOV, MKV, WEBM, M4V — до 30 ГБ
            </span>
          </div>
        )}
      </Step>

      <Step index={3} title="Формат и количество">
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Field label="Соотношение сторон">
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-4 gap-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-1">
                {ASPECTS.map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => actions.setAspect(a)}
                    aria-pressed={state.aspect === a}
                    className={[
                      "flex flex-col items-center justify-center gap-1 rounded-md px-2 py-2 text-xs font-medium transition-colors",
                      state.aspect === a
                        ? "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] shadow-[var(--shadow-xs)]"
                        : "text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]",
                    ].join(" ")}
                  >
                    <span className="font-mono text-[10px]">{a}</span>
                    <span className="text-[10px]">{ASPECT_LABEL[a]}</span>
                  </button>
                ))}
              </div>
              <AspectPreview aspect={state.aspect} />
            </div>
          </Field>

          <Field label="Количество рилсов">
            <div className="flex items-center gap-3">
              <div className="flex rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-1">
                <button
                  type="button"
                  onClick={() => actions.setReelCountMode("auto")}
                  aria-pressed={state.reelCountMode === "auto"}
                  className={[
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    state.reelCountMode === "auto"
                      ? "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] shadow-[var(--shadow-xs)]"
                      : "text-[color:var(--text-muted)]",
                  ].join(" ")}
                >
                  Авто
                </button>
                <button
                  type="button"
                  onClick={() => actions.setReelCountMode("custom")}
                  aria-pressed={state.reelCountMode === "custom"}
                  className={[
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    state.reelCountMode === "custom"
                      ? "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] shadow-[var(--shadow-xs)]"
                      : "text-[color:var(--text-muted)]",
                  ].join(" ")}
                >
                  Вручную
                </button>
              </div>

              <div
                className={`flex flex-1 items-center gap-3 ${
                  state.reelCountMode === "custom"
                    ? ""
                    : "pointer-events-none opacity-40"
                }`}
              >
                <input
                  type="range"
                  min={REEL_COUNT_MIN}
                  max={REEL_COUNT_MAX}
                  value={state.reelCount}
                  onChange={(e) => actions.setReelCount(Number(e.target.value))}
                  disabled={state.reelCountMode !== "custom"}
                  className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-[color:var(--border-default)] accent-[color:var(--accent-primary)]"
                  aria-label="Количество рилсов"
                />
                <input
                  type="number"
                  min={REEL_COUNT_MIN}
                  max={REEL_COUNT_MAX}
                  value={state.reelCount}
                  onChange={(e) => {
                    const raw = Number(e.target.value);
                    if (Number.isNaN(raw)) return;
                    actions.setReelCount(
                      Math.min(
                        REEL_COUNT_MAX,
                        Math.max(REEL_COUNT_MIN, Math.round(raw)),
                      ),
                    );
                  }}
                  disabled={state.reelCountMode !== "custom"}
                  className="w-16 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 text-center font-mono text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)] disabled:opacity-40"
                />
              </div>
            </div>
            <span className="text-[11px] text-[color:var(--text-muted)]">
              В авто-режиме получается около 12 рилсов на каждые 20 минут
              исходного видео.
            </span>
          </Field>
        </div>
      </Step>

      {subtitlePresets.length > 0 && (
        <Step index={4} title="Субтитры">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto]">
            <Field label="Стиль">
              <div className="flex items-center gap-2">
                <select
                  value={state.subtitlePresetId ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    actions.setSubtitlePresetId(raw === "" ? null : Number(raw));
                  }}
                  className="flex-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
                >
                  {subtitlePresets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.is_default ? "★ " : ""}
                      {p.name}
                      {p.is_builtin ? " · встроенный" : ""}
                    </option>
                  ))}
                </select>
                <Link
                  to="/settings/subtitles"
                  className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
                >
                  Редактировать
                </Link>
              </div>
              {state.selectedSubtitlePreset && (
                <p className="text-[11px] text-[color:var(--text-muted)]">
                  {state.selectedSubtitlePreset.style.font} ·{" "}
                  {state.selectedSubtitlePreset.style.size} px ·{" "}
                  {state.selectedSubtitlePreset.style.anchor} ·{" "}
                  {state.selectedSubtitlePreset.style.offset_px} px от края
                </p>
              )}
            </Field>
            {state.selectedSubtitlePreset && (
              <div className="flex justify-end">
                <SubtitlePreview
                  config={state.selectedSubtitlePreset.style}
                  aspect={state.aspect}
                  fitMode={state.fitMode}
                  previewHeight={180}
                  showAnchorGuide={false}
                />
              </div>
            )}
          </div>
        </Step>
      )}

      <Step index={5} title="Пост-продакшн">
        <Field label="Пресет (интро и аутро, нормализация звука, зум)">
          <div className="flex items-center gap-2">
            <select
              value={state.postProductionPresetId ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                actions.setPostProductionPresetId(raw === "" ? null : Number(raw));
              }}
              className="flex-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
            >
              <option value="">— без пост-продакшна —</option>
              {postProductionPresets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.is_default ? "★ " : ""}
                  {p.name}
                </option>
              ))}
            </select>
            <Link
              to="/settings/post-production"
              className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
            >
              {postProductionPresets.length === 0
                ? "Создать"
                : "Редактировать"}
            </Link>
          </div>
        </Field>
        {state.selectedPostProductionPreset && (
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-3">
            <span className="text-[11px] uppercase tracking-wider text-[color:var(--text-muted)]">
              Применить для этого видео
            </span>
            <OverrideCheckbox
              label="интро"
              checked={state.overrides.enable_intro !== false}
              disabled={!state.selectedPostProductionPreset.intro_asset}
              onChange={(v) => actions.setOverride("enable_intro", v)}
            />
            <OverrideCheckbox
              label="аутро"
              checked={state.overrides.enable_outro !== false}
              disabled={!state.selectedPostProductionPreset.outro_asset}
              onChange={(v) => actions.setOverride("enable_outro", v)}
            />
            <OverrideCheckbox
              label="зум"
              checked={state.overrides.enable_zoom !== false}
              disabled={!state.selectedPostProductionPreset.config.zoom_enabled}
              onChange={(v) => actions.setOverride("enable_zoom", v)}
            />
            <OverrideCheckbox
              label="нормализация звука"
              checked={state.overrides.enable_loudnorm !== false}
              disabled={
                !state.selectedPostProductionPreset.config.audio_normalize_enabled
              }
              onChange={(v) => actions.setOverride("enable_loudnorm", v)}
            />
            <OverrideCheckbox
              label="чёрно-белое"
              checked={state.overrides.enable_bw !== false}
              disabled={!state.selectedPostProductionPreset.config.bw_enabled}
              onChange={(v) => actions.setOverride("enable_bw", v)}
            />
          </div>
        )}
        {state.selectedPostProductionPreset?.companion_asset && (
          <div className="mt-3 flex flex-col gap-2 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-3">
            <span className="text-[11px] uppercase tracking-wider text-[color:var(--text-muted)]">
              Split-screen для этого видео
            </span>
            <span className="text-[11px] leading-relaxed text-[color:var(--text-muted)]">
              Пресет содержит companion «{state.selectedPostProductionPreset.companion_asset.name}».
              Переопределяет значение пресета, либо оставь «По пресету».
            </span>
            <div className="flex gap-1 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-1">
              {(["preset", "on", "off"] as const).map((choice) => {
                const active =
                  (choice === "preset" && state.splitScreenOverride === null) ||
                  (choice === "on" && state.splitScreenOverride === true) ||
                  (choice === "off" && state.splitScreenOverride === false);
                return (
                  <button
                    key={choice}
                    type="button"
                    onClick={() => {
                      if (choice === "preset") actions.setSplitScreenOverride(null);
                      else if (choice === "on") actions.setSplitScreenOverride(true);
                      else actions.setSplitScreenOverride(false);
                    }}
                    aria-pressed={active}
                    className={[
                      "flex-1 rounded-[6px] px-2 py-1.5 text-xs font-medium transition-colors",
                      active
                        ? "bg-[color:var(--surface-sunken)] text-[color:var(--text-primary)] shadow-[var(--shadow-xs)]"
                        : "text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]",
                    ].join(" ")}
                  >
                    {choice === "preset"
                      ? "По пресету"
                      : choice === "on"
                        ? "Включить"
                        : "Выключить"}
                  </button>
                );
              })}
            </div>
            {(() => {
              const presetEnabled =
                state.selectedPostProductionPreset.config.split_screen.enabled;
              const effectiveEnabled =
                state.splitScreenOverride === null
                  ? presetEnabled
                  : state.splitScreenOverride;
              if (!effectiveEnabled) return null;
              const companionAssetId =
                state.selectedPostProductionPreset.companion_asset_id;
              return (
                <div className="mt-2 flex flex-col gap-2">
                  <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
                    Превью раскладки
                  </span>
                  <div className="overflow-x-auto">
                    <SplitScreenPreviewEditor
                      config={state.selectedPostProductionPreset.config.split_screen}
                      sourceThumbUrl={state.sourceThumbnailDataUrl}
                      companionThumbUrl={
                        companionAssetId !== null
                          ? `/api/v1/post_production/assets/${companionAssetId}/thumbnail?time_sec=0.5`
                          : null
                      }
                      previewHeight={300}
                      onChange={() => {
                        /* preset config is read-only в wizard'е —
                           редактирование раскладки делается в /settings/post-production */
                      }}
                    />
                  </div>
                  <span className="text-[11px] leading-relaxed text-[color:var(--text-muted)]">
                    {state.sourceThumbnailDataUrl
                      ? "Кадр взят из выбранного видео. Позиционирование настраивается в пресете."
                      : "Выбери видео выше, чтобы увидеть кадр основы в превью."}
                  </span>
                </div>
              );
            })()}
          </div>
        )}
      </Step>

      <Step index={6} title="Дополнительная инструкция (опционально)">
        <Field
          label="Доп-промпт для этого видео"
          help={(
            <>
              Если заполнено — этот текст приклеится в самое начало
              system-prompt всех LLM-вызовов (12 агентов). Используй для
              таргетинга темы, особенностей спикера или стилистических
              правил. Пусто = стандартное поведение.
            </>
          )}
        >
          <textarea
            value={state.customSystemPrompt}
            onChange={(event) => actions.setCustomSystemPrompt(event.target.value)}
            maxLength={8000}
            rows={5}
            placeholder={[
              "Пример:",
              "Главная тема видео — осознанное потребление.",
              "Сделай акцент на парадоксах и неожиданных признаниях.",
              "Избегай цитат про «успех» и «счастье».",
            ].join("\n")}
            className="w-full resize-y rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--border-strong)] focus:outline-none"
            aria-describedby="custom-prompt-help"
          />
          <div
            id="custom-prompt-help"
            className="mt-1 flex justify-between text-[11px] text-[color:var(--text-muted)]"
          >
            <span>Обрезается до 8000 знаков.</span>
            <span aria-live="polite">
              {state.customSystemPrompt.length}/8000
            </span>
          </div>
        </Field>
      </Step>

      <details className="surface-card group p-5 open:shadow-[var(--shadow-sm)]">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-[color:var(--text-primary)]">
          <span className="flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
              Дополнительно
            </span>
            <span>модели, язык, кадрирование, кэш</span>
          </span>
          <svg
            className="text-[color:var(--text-muted)] transition-transform duration-200 group-open:rotate-180"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </summary>

        <div className="mt-5 flex flex-col gap-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Распознавание речи">
              <Select
                value={state.transcriber}
                onChange={actions.setTranscriber}
                options={models.available_transcribers.map((t) => ({
                  value: t,
                  label: t,
                }))}
              />
            </Field>
            <Field label="LLM-провайдер">
              <Select
                value={state.provider}
                onChange={actions.setProvider}
                options={models.available_providers
                  .filter((p) => p === "gemini" || p === "zhipu")
                  .map((p) => ({
                    value: p,
                    label: p,
                  }))}
              />
            </Field>
            <Field label="Режим нейросети">
              <span className="text-[11px] text-[color:var(--text-muted)]">
                Качество vs скорость переключается в
                {" "}
                <a
                  href="/settings/performance"
                  className="underline underline-offset-2 hover:text-[color:var(--text-primary)]"
                >
                  настройках производительности
                </a>
                {" "}
                — там один глобальный переключатель на все стадии.
              </span>
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="Язык исходника">
              <Select
                value={state.sourceLang}
                onChange={(v) => actions.setSourceLang(v as SourceLanguage)}
                options={SOURCE_LANGUAGES.map((l) => ({
                  value: l,
                  label: SOURCE_LANG_LABELS[l],
                }))}
              />
              <span className="text-[11px] text-[color:var(--text-muted)]">
                Не-русский автоматически переведём на русский.
              </span>
            </Field>
            <Field label="Кадрирование">
              <Select
                value={state.fitMode}
                onChange={(v) => actions.setFitMode(v as FitMode)}
                options={FIT_MODES.map((m) => ({
                  value: m,
                  label: FIT_MODE_LABEL[m] || m,
                }))}
              />
              {(() => {
                const preset = state.selectedPostProductionPreset;
                if (!preset) return null;
                const presetEnabled = preset.config.split_screen.enabled;
                const effectiveEnabled =
                  state.splitScreenOverride === null
                    ? presetEnabled
                    : state.splitScreenOverride;
                if (!effectiveEnabled) return null;
                return (
                  <p className="mt-1 text-[11px] leading-relaxed text-[color:var(--warning)]">
                    В split-режиме это кадрирование не применяется. Настрой
                    кроп через Split-Screen Preview в{" "}
                    <Link
                      to="/settings/post-production"
                      className="underline underline-offset-2 hover:text-[color:var(--warning)]"
                    >
                      пост-продакшн пресете
                    </Link>
                    .
                  </p>
                );
              })()}
            </Field>
          </div>

          <ToggleRow
            id="use_proxy"
            label="Готовить рабочую копию 1080p"
            hint="Делаем лёгкую 1080p версию и работаем с ней. На 4K источниках ускоряет обработку в три-пять раз."
            checked={state.useProxy}
            onChange={actions.setUseProxy}
          />
          <ToggleRow
            id="use_source_for_render"
            label="Финальный рендер из оригинала"
            hint="Берём для сборки исходное 4K. Дольше, но максимальное качество."
            checked={state.useSourceForRender}
            onChange={actions.setUseSourceForRender}
            disabled={!state.useProxy}
            disabledReason="Доступно, когда включена рабочая копия 1080p."
          />
          <ToggleRow
            id="force_reingest"
            label="Перетранскрибировать заново"
            hint="Если менял настройки распознавания или уверен, что предыдущая транскрипция была неточной. Обычно нужен редко — тот же файл читаем из кэша моментально."
            checked={state.forceReingest}
            onChange={actions.setForceReingest}
          />
        </div>
      </details>

      <div className="flex flex-col gap-2 rounded-lg border border-[color:var(--line-soft)] bg-[color:var(--ink-2)] p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-stone-500">
          Режим монтажа
        </div>
        <div className="flex gap-3">
          <label className="flex cursor-pointer items-start gap-2 rounded-md border border-[color:var(--line-soft)] bg-white px-3 py-2 text-sm hover:border-[color:var(--line)] has-[:checked]:border-[color:var(--gold)] has-[:checked]:bg-[color:var(--ink-3)]">
            <input
              type="radio"
              name="pipeline_mode"
              value="auto"
              checked={state.pipelineMode === "auto"}
              onChange={() => actions.setPipelineMode("auto")}
              className="mt-0.5"
            />
            <span>
              <span className="block font-medium text-stone-900">
                Автоматический (рекомендовано)
              </span>
              <span className="text-xs text-stone-500">
                Робот-монтажёр проанализирует дорожку и сам примет решения
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer items-start gap-2 rounded-md border border-[color:var(--line-soft)] bg-white px-3 py-2 text-sm hover:border-[color:var(--line)] has-[:checked]:border-[color:var(--gold)] has-[:checked]:bg-[color:var(--ink-3)]">
            <input
              type="radio"
              name="pipeline_mode"
              value="manual"
              checked={state.pipelineMode === "manual"}
              onChange={() => actions.setPipelineMode("manual")}
              className="mt-0.5"
            />
            <span>
              <span className="block font-medium text-stone-900">Ручной</span>
              <span className="text-xs text-stone-500">
                Использовать настройки из /settings/performance
              </span>
            </span>
          </label>
        </div>
        <p className="pt-1 text-[11px] leading-relaxed text-stone-500">
          Автоматический режим решает за склейки, темп, акценты, сжатие пауз,
          движение камеры. Формат кадра, модель распознавания, зум, интро/аутро
          и чёрно-белый режим остаются под твоим контролем — их Auto не трогает.
        </p>
      </div>

      <ComposerStrategyBlock
        value={state.composerStrategy}
        onChange={actions.setComposerStrategy}
      />

      <button
        onClick={actions.submit}
        disabled={
          !state.file ||
          state.uploading ||
          state.autoAnalyzing ||
          !!state.autoAnalysis
        }
        className="mt-2 inline-flex items-center justify-center gap-2 self-start rounded-lg bg-[color:var(--accent-primary)] px-6 py-3 text-sm font-semibold text-[color:var(--accent-on-primary)] shadow-[var(--shadow-sm)] transition-all duration-150 hover:bg-[color:var(--accent-primary-hover)] hover:shadow-[var(--shadow-md)] disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)] disabled:shadow-none"
        type="button"
      >
        {state.uploading ? (
          <>
            <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Загружаем видео…
          </>
        ) : state.autoAnalyzing ? (
          <>
            <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Робот анализирует дорожку…
          </>
        ) : (
          "Запустить нарезку"
        )}
      </button>

      {state.profileSuggestion &&
        state.profileSuggestion.profile !== state.visionProfile && (
          <div className="flex flex-col gap-2 rounded-lg border border-[color:var(--accent-primary)]/30 bg-[color:var(--accent-primary-subtle)] p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-[color:var(--text-primary)]">
                Рекомендуем профиль:{" "}
                {PROFILE_LABEL[state.profileSuggestion.profile] ??
                  state.profileSuggestion.profile}
              </span>
              <span className="font-mono text-[11px] text-[color:var(--text-muted)]">
                уверенность{" "}
                {Math.round(state.profileSuggestion.confidence * 100)}%
              </span>
            </div>
            {state.profileSuggestion.reasons.length > 0 && (
              <ul className="list-disc pl-5 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
                {state.profileSuggestion.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
            {state.profileSuggestionApplied ? (
              <span className="text-[12px] font-medium text-[color:var(--success)]">
                Профиль применён к этому джобу.
              </span>
            ) : (
              <button
                type="button"
                onClick={actions.applyProfileSuggestion}
                className="self-start rounded-lg bg-[color:var(--accent-primary)] px-4 py-2 text-xs font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)]"
              >
                Применить рекомендованный профиль
              </button>
            )}
          </div>
        )}

      {state.autoAnalysis && (
        <AutoConfigSummary
          data={state.autoAnalysis}
          onAccept={actions.acceptAutoConfig}
          onSwitchToManual={actions.switchToManual}
        />
      )}

      {state.error && (
        <div
          role="alert"
          className="rounded-lg border border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 p-3 text-sm text-[color:var(--danger)]"
        >
          {state.error}
        </div>
      )}

      {state.jobId && state.sse.lastEvent && (
        <div className="surface-card p-4">
          <div className="mb-2 flex items-center justify-between text-xs text-[color:var(--text-secondary)]">
            <span>
              <span className="font-mono text-[color:var(--text-muted)]">
                {state.jobId.slice(0, 8)}
              </span>{" "}
              · стадия{" "}
              <span className="text-[color:var(--text-primary)]">
                {state.sse.lastEvent.stage ?? "…"}
              </span>
            </span>
            <span className="font-mono text-[color:var(--text-primary)]">
              {state.sse.lastEvent.progress ?? 0}%
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
            <div
              className="h-full gradient-accent transition-all duration-500"
              style={{ width: `${state.sse.lastEvent.progress ?? 0}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-[color:var(--text-muted)]">
            {state.sse.lastEvent.message ?? "…"}
          </p>
          {state.sse.finalStatus === "error" && state.sse.lastEvent.error && (
            <p className="mt-2 text-xs text-[color:var(--danger)]">
              Ошибка: {state.sse.lastEvent.error}
            </p>
          )}
          {state.sse.finalStatus === "done" && (
            <Link
              to={`/jobs/${state.jobId}`}
              className="mt-3 inline-block text-xs font-medium text-[color:var(--accent-primary)] hover:text-[color:var(--accent-primary-hover)]"
            >
              Открыть детали →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
