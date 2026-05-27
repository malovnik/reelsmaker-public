/**
 * Пошаговый режим (guided) — линейная машина шагов «один экран = один выбор».
 *
 * СТАРТ → S1 Проект → S2 Видео → S3 Вид → S4 Субтитры → S5 Обработка →
 * S6 Модели → S7 Запуск → S8 Прогресс → (готово → переход к результатам джоба).
 *
 * Источник состояния — общий WizardStateProvider (через useWizardStateContext),
 * один на оба режима: переключение Пошаговый↔Эксперт ничего не теряет.
 * Шаги S1–S6 листаются назад/вперёд свободно; после запуска (S7) — точка
 * невозврата. На каждом шаге дефолт уже выбран → Auto-режим для новичка.
 */
import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FIT_MODES,
  api,
  type FitMode,
  type ModelsInfo,
  type ProfileMaskRead,
  type SubtitleStylePreset,
} from "@/lib/api";
import { cn } from "@/components/ui";
import { useToast, useConfirm, useWizardStateContext } from "@/contexts";
import { SubtitlePreview } from "@/components/SubtitlePreview";
import { VideoPreviewCard } from "@/components/upload/VideoPreviewCard";
import { NARRATIVE_MODES, type NarrativeMode } from "@/components/upload/useWizardState";
import {
  BackNext,
  SetupProgress,
  StepShell,
} from "@/components/upload/guided/StepChrome";
import {
  NO_TRANSCRIBER_MESSAGE,
  transcriberLabel,
} from "@/lib/constants/transcribers";

const ACCEPTED = [".mp4", ".mov", ".mkv", ".webm", ".m4v"];

/** Короткое пояснение под каждым движком для Пошагового режима. */
const TRANSCRIBER_DESC: Record<string, string> = {
  stable_ts_mlx: "Бесплатно, видео не уходит в интернет. Точные тайминги.",
  mlx_whisper: "Бесплатно и локально, видео не уходит в интернет.",
  deepgram: "Облако: точнее, но нужен ключ и оплата.",
};

function isAcceptedFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  const lower = file.name.toLowerCase();
  return ACCEPTED.some((ext) => lower.endsWith(ext));
}

/** Человеческие имена видов нарезки + что обещаем. Служебное имя — мелко серым. */
const NARRATIVE_META: Record<
  NarrativeMode,
  { name: string; desc: string; recommended?: boolean }
> = {
  bottom_up: {
    name: "Режиссёрский",
    desc: "Самый внимательный. Ищет крючки и эмоции, собирает завязку, кульминацию и развязку. Считает дольше, результат сильнее.",
    recommended: true,
  },
  map_reduce: {
    name: "Сбалансированный",
    desc: "Как у популярных сервисов: быстро находит сильные куски, без глубокой драматургии.",
  },
  viral_2026: {
    name: "Быстрый",
    desc: "Самый шустрый. Режет по вирусным сигналам, собирает клипы из нескольких кусков. Ждать меньше всего.",
  },
};

/** Понятные пользователю переключатели обработки → ключи overrides пресета. */
type ProcessKey = "enable_zoom" | "enable_intro";
const PROCESS_ROWS: {
  key: ProcessKey;
  label: string;
  hint: string;
}[] = [
  {
    key: "enable_zoom",
    label: "Приближение на акцентах",
    hint: "Лёгкий зум в важные моменты речи.",
  },
  {
    key: "enable_intro",
    label: "Интро и аутро",
    hint: "Подставить заставку из пресета в начало и конец рилса.",
  },
];

interface Props {
  models: ModelsInfo;
  subtitlePresets: SubtitleStylePreset[];
  profileMasks: ProfileMaskRead[];
  /** Переход в Эксперт-режим (ссылка «продвинутые настройки →»). */
  onOpenExpert: () => void;
}

type Screen =
  | "start"
  | 1
  | 2
  | 3
  | 4
  | 5
  | 6
  | "summary"
  | "progress";

const FIT_MODE_LABEL: Record<FitMode, string> = {
  fill: "Заполнить кадр",
  fit: "Сохранить весь кадр",
};

export function GuidedFlow({
  models,
  subtitlePresets,
  onOpenExpert,
}: Props) {
  const { state, actions } = useWizardStateContext();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const [screen, setScreen] = useState<Screen>("start");
  const [projectName, setProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [isDragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const goSetup = useCallback((step: number) => setScreen(step as Screen), []);

  // ── S2: выбор файла ───────────────────────────────────────────────
  const pickFile = useCallback(
    (picked: File | undefined) => {
      if (!picked) return;
      if (!isAcceptedFile(picked)) {
        toast.error("Не тот формат файла", {
          detail: `Подходят ${ACCEPTED.join(", ")}. Выбран: ${picked.name}`,
        });
        return;
      }
      actions.applySelectedFile(picked);
    },
    [actions, toast],
  );

  // ── S1 → S2: создаём/выбираем проект, затем шлём project_id ────────
  const leaveProjectStep = useCallback(async () => {
    if (state.projectId !== null) {
      setScreen(2);
      return;
    }
    setCreatingProject(true);
    try {
      const now = new Date();
      const auto = `Проект · ${now.toLocaleDateString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
      })} ${now.toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
      const project = await api.createProject({
        name: projectName.trim() || auto,
      });
      actions.setProjectId(project.id);
      setScreen(2);
    } catch (err) {
      toast.showError(err);
    } finally {
      setCreatingProject(false);
    }
  }, [actions, projectName, state.projectId, toast]);

  // ── S7 → S8: запуск нарезки ───────────────────────────────────────
  const launch = useCallback(async () => {
    setScreen("progress");
    await actions.submit();
  }, [actions]);

  // ── S8: отмена ────────────────────────────────────────────────────
  const cancelJob = useCallback(async () => {
    const ok = await confirm({
      title: "Отменить нарезку?",
      description: "Уже сделанная работа пропадёт. Видео останется загруженным.",
      confirmLabel: "Отменить нарезку",
      cancelLabel: "Продолжить",
      destructive: true,
    });
    if (!ok) return;
    await actions.cancel();
    toast.info("Нарезка отменена");
  }, [actions, confirm, toast]);

  const finish = useCallback(() => {
    actions.reset();
    setProjectName("");
    setScreen("start");
  }, [actions]);

  // Готово → ведём к результатам джоба (S9 живёт на странице джоба).
  const sseDone = state.sse.finalStatus === "done";
  const sseError = state.sse.finalStatus === "error";

  if (models.available_providers.length === 0) {
    return (
      <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-5 text-sm text-[var(--danger)]">
        Нужен ключ ИИ-провайдера. Добавьте <code>GEMINI_API_KEY</code> в файл{" "}
        <code>.env</code> и перезапустите сервер командой <code>./run.sh</code>.
      </div>
    );
  }

  // ── СТАРТ ──────────────────────────────────────────────────────────
  if (screen === "start") {
    return (
      <div className="fade-in flex flex-col items-center gap-6 py-12 text-center">
        <span className="font-[family-name:var(--font-pixel)] text-[0.625rem] uppercase tracking-[0.1em] text-[var(--copper)]">
          // Новый проект
        </span>
        <h2 className="max-w-[16ch] font-[family-name:var(--font-display)] text-3xl leading-tight text-[var(--gold)] sm:text-4xl">
          Длинное видео — в десятки вертикальных рилсов
        </h2>
        <p className="max-w-[44ch] text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
          Веду за руку, один шаг за раз. Всё уже настроено по умолчанию — можно
          просто нажимать «Далее».
        </p>
        <button
          type="button"
          className="btn btn-primary mt-2 px-10 py-4 text-base"
          onClick={() => setScreen(1)}
        >
          Создать проект
        </button>
        <button
          type="button"
          onClick={onOpenExpert}
          className="link font-[family-name:var(--font-mono)] text-[0.75rem] uppercase tracking-[0.12em]"
        >
          Уже настраивал раньше? Открыть продвинутые настройки →
        </button>
      </div>
    );
  }

  // ── S1 Проект ──────────────────────────────────────────────────────
  if (screen === 1) {
    return (
      <StepShell
        tag="// Проект"
        title="Куда сложить рилсы?"
        lead="Проект — это папка для одной нарезки. Так рилсы не смешаются с прошлыми."
        progress={<SetupProgress current={1} onJump={goSetup} />}
        footer={
          <BackNext
            onBack={() => setScreen("start")}
            onNext={leaveProjectStep}
            nextLabel={creatingProject ? "Создаём…" : "Далее →"}
            nextDisabled={creatingProject}
          />
        }
      >
        <label className="flex flex-col gap-2">
          <span className="text-[0.8125rem] font-medium text-[var(--paper)]">
            Название проекта
          </span>
          <input
            type="text"
            value={projectName}
            onChange={(e) => {
              setProjectName(e.target.value);
              if (state.projectId !== null) actions.setProjectId(null);
            }}
            placeholder="Подкаст, выпуск 12"
            className="w-full border border-[var(--line)] bg-[var(--ink-3)] px-3.5 py-3 text-sm text-[var(--paper)] outline-none placeholder:text-[var(--mute)] focus:border-[var(--gold)]"
          />
          <span className="text-[0.75rem] text-[var(--mute)]">
            Оставьте пустым — придумаем имя с датой и временем.
          </span>
        </label>

        {state.projects.length > 0 && (
          <div className="flex flex-col gap-3">
            <span className="text-[0.8125rem] text-[var(--mute-2)]">
              Или продолжить в существующем:
            </span>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {state.projects.map((p) => {
                const active = state.projectId === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      actions.setProjectId(active ? null : p.id);
                      setProjectName("");
                    }}
                    aria-pressed={active}
                    className={cn(
                      "flex flex-col items-start gap-1 border bg-[var(--ink-2)] p-4 text-left transition-colors",
                      active
                        ? "border-[var(--gold)]"
                        : "border-[var(--line)] hover:border-[var(--gold)]",
                    )}
                  >
                    <span className="text-sm font-medium text-[var(--paper)]">
                      {p.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </StepShell>
    );
  }

  // ── S2 Видео ────────────────────────────────────────────────────────
  if (screen === 2) {
    return (
      <StepShell
        tag="// Исходник"
        title="Загрузите видео"
        progress={<SetupProgress current={2} onJump={goSetup} />}
        footer={
          <BackNext
            onBack={() => setScreen(1)}
            onNext={() => setScreen(3)}
            nextDisabled={!state.file}
            nextHint="Сначала выберите видеофайл."
          />
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          onChange={(e) => pickFile(e.target.files?.[0])}
          className="hidden"
        />
        {state.file ? (
          <VideoPreviewCard
            file={state.file}
            onRemove={actions.clearSelectedFile}
          />
        ) : (
          <div
            role="button"
            tabIndex={0}
            aria-label="Область загрузки видео"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pickFile(e.dataTransfer.files[0]);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 border border-dashed p-12 text-center transition-colors",
              isDragging
                ? "border-[var(--gold)] bg-[var(--accent-soft)]"
                : "border-[var(--line)] bg-[var(--ink-3)] hover:border-[var(--gold)]",
            )}
          >
            <span className="text-sm font-medium text-[var(--paper)]">
              Перетащите файл сюда
            </span>
            <span className="text-[0.8125rem] text-[var(--mute-2)]">
              или нажмите, чтобы выбрать
            </span>
            <span className="mt-1 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.12em] text-[var(--mute)]">
              MP4, MOV, MKV · до 30 ГБ
            </span>
          </div>
        )}
      </StepShell>
    );
  }

  // ── S3 Вид рилсов ────────────────────────────────────────────────────
  if (screen === 3) {
    return (
      <StepShell
        tag="// Вид рилсов"
        title="Как нарезать?"
        progress={<SetupProgress current={3} onJump={goSetup} />}
        footer={
          <BackNext onBack={() => setScreen(2)} onNext={() => setScreen(4)} />
        }
      >
        <div className="flex flex-col gap-3">
          {NARRATIVE_MODES.map((mode) => {
            const meta = NARRATIVE_META[mode];
            const active = state.narrativeMode === mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => actions.setNarrativeMode(mode)}
                aria-pressed={active}
                className={cn(
                  "flex flex-col items-start gap-2 border bg-[var(--ink-2)] p-5 text-left transition-colors",
                  active
                    ? "border-2 border-[var(--gold)]"
                    : "border border-[var(--line)] hover:border-[var(--gold)]",
                )}
              >
                <span className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "inline-block size-3 rounded-full is-round border",
                      active
                        ? "border-[var(--gold)] bg-[var(--gold)]"
                        : "border-[var(--mute)]",
                    )}
                  />
                  <span className="text-base font-medium text-[var(--paper)]">
                    {meta.name}
                  </span>
                  {meta.recommended && (
                    <span className="font-[family-name:var(--font-pixel)] text-[0.5rem] uppercase tracking-[0.08em] text-[var(--gold)]">
                      Рекомендуем
                    </span>
                  )}
                </span>
                <span className="text-[0.875rem] leading-relaxed text-[var(--mute-2)]">
                  {meta.desc}
                </span>
                <span className="font-[family-name:var(--font-mono)] text-[0.625rem] text-[var(--mute)]">
                  {mode}
                </span>
              </button>
            );
          })}
        </div>
      </StepShell>
    );
  }

  // ── S4 Субтитры ───────────────────────────────────────────────────────
  if (screen === 4) {
    return (
      <StepShell
        tag="// Субтитры"
        title="Как подписать речь?"
        progress={<SetupProgress current={4} onJump={goSetup} />}
        footer={
          <BackNext onBack={() => setScreen(3)} onNext={() => setScreen(5)} />
        }
      >
        {subtitlePresets.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {subtitlePresets.map((preset) => {
              const active =
                !state.subtitlesOff && state.subtitlePresetId === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => {
                    actions.setSubtitlesOff(false);
                    actions.setSubtitlePresetId(preset.id);
                  }}
                  aria-pressed={active}
                  className={cn(
                    "flex flex-col items-center gap-3 border bg-[var(--ink-2)] p-3 transition-colors",
                    active
                      ? "border-2 border-[var(--gold)]"
                      : "border border-[var(--line)] hover:border-[var(--gold)]",
                  )}
                >
                  <SubtitlePreview
                    config={preset.style}
                    aspect={state.aspect}
                    fitMode={state.fitMode}
                    previewHeight={150}
                    showAnchorGuide={false}
                  />
                  <span className="text-sm font-medium text-[var(--paper)]">
                    {preset.name}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        <label className="flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={state.subtitlesOff}
            onChange={(e) => actions.setSubtitlesOff(e.target.checked)}
            className="size-4 accent-[var(--gold)]"
          />
          <span className="text-[0.9375rem] text-[var(--paper)]">
            Без субтитров — оставить как есть
          </span>
        </label>
      </StepShell>
    );
  }

  // ── S5 Обработка ──────────────────────────────────────────────────────
  if (screen === 5) {
    const preset = state.selectedPostProductionPreset;
    return (
      <StepShell
        tag="// Обработка"
        title="Что добавить к рилсам?"
        lead="Всё по умолчанию выключено. Включайте только нужное — каждое добавляет время рендера."
        progress={<SetupProgress current={5} onJump={goSetup} />}
        footer={
          <BackNext onBack={() => setScreen(4)} onNext={() => setScreen(6)} />
        }
      >
        <div className="flex flex-col divide-y divide-[var(--line)] border border-[var(--line)]">
          {PROCESS_ROWS.map((row) => {
            const presetSupports =
              row.key === "enable_zoom"
                ? !!preset?.config.zoom_enabled
                : !!preset?.intro_asset || !!preset?.outro_asset;
            const checked =
              presetSupports && state.overrides[row.key] !== false;
            return (
              <div
                key={row.key}
                className="flex items-start justify-between gap-4 p-4"
              >
                <div className="min-w-0">
                  <span className="text-[0.9375rem] font-medium text-[var(--paper)]">
                    {row.label}
                  </span>
                  <p className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
                    {presetSupports
                      ? row.hint
                      : "Недоступно в текущем пресете пост-обработки."}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={checked}
                  disabled={!presetSupports}
                  onClick={() => actions.setOverride(row.key, !checked)}
                  className={cn(
                    "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center border transition-colors disabled:opacity-40",
                    checked
                      ? "border-[var(--gold)] bg-[var(--gold)]"
                      : "border-[var(--line)] bg-[var(--ink-3)]",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "block size-4 transition-transform",
                      checked
                        ? "translate-x-6 bg-[var(--ink)]"
                        : "translate-x-1 bg-[var(--mute-2)]",
                    )}
                  />
                </button>
              </div>
            );
          })}
          {(() => {
            const splitSupported = !!preset?.companion_asset;
            const splitChecked =
              splitSupported &&
              (state.splitScreenOverride ??
                !!preset?.config.split_screen.enabled);
            return (
              <div className="flex items-start justify-between gap-4 p-4">
                <div className="min-w-0">
                  <span className="text-[0.9375rem] font-medium text-[var(--paper)]">
                    Сплит-скрин
                  </span>
                  <p className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
                    {splitSupported
                      ? "Наложить видео-компаньон из пресета (реакция / вторая камера)."
                      : "Сначала добавьте видео-компаньон в пресете пост-продакшн (Эксперт → Пост-продакшн)."}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={splitChecked}
                  disabled={!splitSupported}
                  onClick={() =>
                    actions.setSplitScreenOverride(!splitChecked)
                  }
                  className={cn(
                    "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center border transition-colors disabled:opacity-40",
                    splitChecked
                      ? "border-[var(--gold)] bg-[var(--gold)]"
                      : "border-[var(--line)] bg-[var(--ink-3)]",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "block size-4 transition-transform",
                      splitChecked
                        ? "translate-x-6 bg-[var(--ink)]"
                        : "translate-x-1 bg-[var(--mute-2)]",
                    )}
                  />
                </button>
              </div>
            );
          })()}
          <div className="flex items-start justify-between gap-4 p-4">
            <div className="min-w-0">
              <span className="text-[0.9375rem] font-medium text-[var(--paper)]">
                Выровнять громкость
              </span>
              <p className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--mute)]">
                Единый уровень звука во всех рилсах. Всегда включено.
              </p>
            </div>
            <span className="mt-0.5 inline-flex h-6 w-11 shrink-0 items-center border border-[var(--gold)] bg-[var(--gold)]">
              <span
                aria-hidden="true"
                className="block size-4 translate-x-6 bg-[var(--ink)]"
              />
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenExpert}
          className="link self-start font-[family-name:var(--font-mono)] text-[0.75rem] uppercase tracking-[0.12em]"
        >
          Тонкая ручная настройка →
        </button>
      </StepShell>
    );
  }

  // ── S6 Модели ─────────────────────────────────────────────────────────
  if (screen === 6) {
    const transcribers = models.available_transcribers;
    const providers = models.available_providers.filter(
      (p) => p === "gemini" || p === "zhipu",
    );
    return (
      <StepShell
        tag="// Модели"
        title="Чем распознавать и думать?"
        progress={<SetupProgress current={6} onJump={goSetup} />}
        footer={
          <BackNext
            onBack={() => setScreen(5)}
            onNext={() => setScreen("summary")}
            nextLabel="К запуску →"
          />
        }
      >
        <div className="flex flex-col gap-2">
          <span className="text-[0.8125rem] font-medium text-[var(--paper)]">
            Распознавание речи
          </span>
          {transcribers.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {transcribers.map((t) => (
                <RadioCard
                  key={t}
                  active={state.transcriber === t}
                  onClick={() => actions.setTranscriber(t)}
                  title={transcriberLabel(t)}
                  desc={TRANSCRIBER_DESC[t] ?? ""}
                />
              ))}
            </div>
          ) : (
            <div className="border border-[var(--copper)] bg-[var(--ink-2)] p-4">
              <p className="text-[0.8125rem] leading-relaxed text-[var(--copper)]">
                {NO_TRANSCRIBER_MESSAGE}
              </p>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[0.8125rem] font-medium text-[var(--paper)]">
            Кто пишет сценарий нарезки
          </span>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {providers.map((p) => (
              <RadioCard
                key={p}
                active={state.provider === p}
                onClick={() => actions.setProvider(p)}
                title={p === "gemini" ? "Gemini" : "Zhipu / GLM"}
                desc={
                  p === "gemini"
                    ? "Проверенный, быстрый. По умолчанию."
                    : "Альтернативная модель."
                }
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[0.8125rem] font-medium text-[var(--paper)]">
            Кадрирование
          </span>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {FIT_MODES.map((m) => (
              <RadioCard
                key={m}
                active={state.fitMode === m}
                onClick={() => actions.setFitMode(m as FitMode)}
                title={FIT_MODE_LABEL[m as FitMode]}
                desc={
                  m === "fill"
                    ? "Кадр заполнен, лицо в центре."
                    : "Виден весь кадр, по бокам поля."
                }
              />
            ))}
          </div>
        </div>

        <div className="border border-[var(--copper)] bg-[var(--ink-2)] p-4">
          <p className="text-[0.8125rem] leading-relaxed text-[var(--copper)]">
            Сейчас все режимы качества работают одинаково — мощная модель пока не
            подключена. Не переплатите за ожидание.
          </p>
        </div>
      </StepShell>
    );
  }

  // ── S7 Сводка ─────────────────────────────────────────────────────────
  if (screen === "summary") {
    const subtitleName = state.subtitlesOff
      ? "Без субтитров"
      : state.selectedSubtitlePreset?.name ?? "—";
    const rows: { label: string; value: string; step?: number }[] = [
      {
        label: "Проект",
        value:
          (state.projectId
            ? state.projects.find((p) => p.id === state.projectId)?.name
            : projectName) ||
          projectName ||
          "Новый",
        step: 1,
      },
      { label: "Видео", value: state.file?.name ?? "—", step: 2 },
      {
        label: "Вид",
        value: NARRATIVE_META[state.narrativeMode].name,
        step: 3,
      },
      { label: "Субтитры", value: subtitleName, step: 4 },
      {
        label: "Модели",
        value: `${
          state.transcriber ? transcriberLabel(state.transcriber) : "—"
        } · ${state.provider === "gemini" ? "Gemini" : "Zhipu"}`,
        step: 6,
      },
    ];
    return (
      <StepShell
        tag="// Проверь и запускай"
        title="Всё готово"
        footer={
          <BackNext onBack={() => setScreen(6)} backLabel="← Назад к настройкам" />
        }
      >
        <div className="border border-[var(--line)] bg-[var(--ink-2)]">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-4 py-3 last:border-b-0"
            >
              <span className="font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.12em] text-[var(--mute)]">
                {row.label}
              </span>
              <span className="min-w-0 flex-1 truncate text-right text-sm text-[var(--paper)]">
                {row.value}
              </span>
              {row.step && (
                <button
                  type="button"
                  onClick={() => setScreen(row.step as Screen)}
                  className="link shrink-0 font-[family-name:var(--font-mono)] text-[0.6875rem] uppercase tracking-[0.1em]"
                >
                  измен.
                </button>
              )}
            </div>
          ))}
        </div>
        <button
          type="button"
          className="btn btn-primary self-center px-10 py-4 text-base"
          onClick={launch}
          disabled={!state.file || state.uploading}
        >
          {state.uploading ? "Запускаем…" : "▶ Запустить нарезку"}
        </button>
      </StepShell>
    );
  }

  // ── S8 Прогресс ───────────────────────────────────────────────────────
  const ev = state.sse.lastEvent;
  const progress = ev?.progress ?? (state.uploading ? 0 : 0);
  return (
    <div className="fade-in flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="font-[family-name:var(--font-pixel)] text-[0.625rem] uppercase tracking-[0.1em] text-[var(--copper)]">
          // {sseDone ? "Готово" : sseError ? "Сбой" : "Идёт нарезка"}
        </span>
        <h2 className="font-[family-name:var(--font-display)] text-2xl text-[var(--paper)]">
          {sseDone
            ? "Рилсы собраны"
            : sseError
              ? "Нарезка прервалась"
              : "Работаю над нарезкой"}
        </h2>
      </div>

      {!sseDone && !sseError && (
        <>
          <div className="h-1.5 w-full bg-[var(--ink-3)]">
            <div
              className="h-full bg-[var(--gold)] transition-[width] duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--paper)]">
              {state.uploading
                ? "Загружаю видео…"
                : ev?.message ?? "Запускаю обработку…"}
            </span>
            <span className="font-[family-name:var(--font-mono)] text-[var(--gold)]">
              {progress}%
            </span>
          </div>
          <button
            type="button"
            className="btn btn-danger self-start"
            onClick={cancelJob}
            disabled={!state.jobId || state.cancelling}
          >
            {state.cancelling ? "Отменяю…" : "✕ Отменить нарезку"}
          </button>
          <p className="text-[0.8125rem] text-[var(--mute)]">
            Можно закрыть вкладку — нарезка не прервётся.
          </p>
        </>
      )}

      {sseError && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-[var(--danger)]">
            {state.sse.error ?? ev?.error ?? "Не удалось завершить нарезку."}
          </p>
          <button type="button" className="btn btn-primary self-start" onClick={finish}>
            Попробовать снова
          </button>
        </div>
      )}

      {sseDone && state.jobId && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-[var(--mute-2)]">
            Рилсы готовы. Откройте галерею, чтобы отобрать лучшие и опубликовать.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate(`/jobs/${state.jobId}`)}
            >
              Смотреть рилсы →
            </button>
            <button type="button" className="btn btn-ghost" onClick={finish}>
              Новый проект
            </button>
          </div>
        </div>
      )}

      {state.error && (
        <div
          role="alert"
          className="border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"
        >
          <span className="font-medium">{state.error.title}</span>
          <span className="block text-[var(--mute-2)]">{state.error.detail}</span>
        </div>
      )}
    </div>
  );
}

interface RadioCardProps {
  active: boolean;
  onClick: () => void;
  title: string;
  desc: string;
  disabled?: boolean;
}

function RadioCard({ active, onClick, title, desc, disabled }: RadioCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cn(
        "flex flex-col items-start gap-1 border bg-[var(--ink-2)] p-4 text-left transition-colors disabled:opacity-40",
        active
          ? "border-2 border-[var(--gold)]"
          : "border border-[var(--line)] hover:border-[var(--gold)]",
      )}
    >
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={cn(
            "inline-block size-3 rounded-full is-round border",
            active ? "border-[var(--gold)] bg-[var(--gold)]" : "border-[var(--mute)]",
          )}
        />
        <span className="text-sm font-medium text-[var(--paper)]">{title}</span>
      </span>
      <span className="text-[0.8125rem] leading-snug text-[var(--mute-2)]">
        {desc}
      </span>
    </button>
  );
}
