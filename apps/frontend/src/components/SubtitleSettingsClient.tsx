
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  DEFAULT_SUBTITLE_STYLE,
  type FontListResponse,
  type SubtitleStyleConfig,
  type SubtitleStylePreset,
} from "@/lib/api";
import { SubtitlePreview } from "@/components/SubtitlePreview";
import { SubtitleStyleEditor } from "@/components/SubtitleStyleEditor";

const FAVOURITES_KEY = "videomaker:favourite-fonts";

interface Props {
  initialPresets: SubtitleStylePreset[];
  initialFonts: FontListResponse;
}

type Mode = { kind: "existing"; presetId: number } | { kind: "new" };

export function SubtitleSettingsClient({
  initialPresets,
  initialFonts,
}: Props) {
  const [fontsState, setFontsState] = useState<FontListResponse>(initialFonts);
  const [refreshingFonts, setRefreshingFonts] = useState(false);
  const [presets, setPresets] =
    useState<SubtitleStylePreset[]>(initialPresets);
  const [mode, setMode] = useState<Mode>(() =>
    initialPresets[0]
      ? { kind: "existing", presetId: initialPresets[0].id }
      : { kind: "new" },
  );
  const [draftStyle, setDraftStyle] = useState<SubtitleStyleConfig>(
    () => initialPresets[0]?.style ?? DEFAULT_SUBTITLE_STYLE,
  );
  const [draftName, setDraftName] = useState<string>(
    () => initialPresets[0]?.name ?? "Мой стиль",
  );
  const [previewAspect, setPreviewAspect] = useState<string>("9:16");
  const [previewFitMode, setPreviewFitMode] = useState<"fill" | "fit">("fill");
  const [favourites, setFavourites] = useState<string[]>([]);
  const [flash, setFlash] = useState<{
    kind: "ok" | "error";
    message: string;
  } | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    return () => {
      if (flashTimerRef.current !== null) {
        clearTimeout(flashTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(FAVOURITES_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setFavourites(parsed.filter((v) => typeof v === "string"));
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const toggleFavourite = useCallback((font: string) => {
    setFavourites((prev) => {
      const next = prev.includes(font)
        ? prev.filter((f) => f !== font)
        : [...prev, font];
      try {
        window.localStorage.setItem(FAVOURITES_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const current = useMemo(
    () =>
      mode.kind === "existing"
        ? presets.find((p) => p.id === mode.presetId) ?? null
        : null,
    [mode, presets],
  );

  const selectPreset = useCallback((preset: SubtitleStylePreset) => {
    setMode({ kind: "existing", presetId: preset.id });
    setDraftStyle(preset.style);
    setDraftName(preset.name);
    setFlash(null);
  }, []);

  const startNewPreset = useCallback(() => {
    setMode({ kind: "new" });
    setDraftStyle(DEFAULT_SUBTITLE_STYLE);
    setDraftName("Новый пресет");
    setFlash(null);
  }, []);

  const showFlash = useCallback(
    (kind: "ok" | "error", message: string) => {
      setFlash({ kind, message });
      if (flashTimerRef.current !== null) {
        clearTimeout(flashTimerRef.current);
      }
      flashTimerRef.current = setTimeout(() => {
        setFlash(null);
        flashTimerRef.current = null;
      }, 3000);
    },
    [],
  );

  const handleCreate = useCallback(async () => {
    if (!draftName.trim()) {
      showFlash("error", "Введи название — без него пресет не сохранится");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createSubtitlePreset({
        name: draftName.trim(),
        style: draftStyle,
        is_default: false,
      });
      setPresets((prev) => [...prev, created]);
      setMode({ kind: "existing", presetId: created.id });
      showFlash("ok", `«${created.name}» создан`);
    } catch (err) {
      showFlash("error", extractError(err));
    } finally {
      setSaving(false);
    }
  }, [draftName, draftStyle, showFlash]);

  const handleUpdate = useCallback(async () => {
    if (mode.kind !== "existing" || current === null) return;
    if (current.is_builtin) {
      showFlash(
        "error",
        "Это встроенный пресет — сделай на его основе свой через «Сохранить как…»",
      );
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateSubtitlePreset(current.id, {
        name: draftName.trim(),
        style: draftStyle,
      });
      setPresets((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      showFlash("ok", "Сохранено");
    } catch (err) {
      showFlash("error", extractError(err));
    } finally {
      setSaving(false);
    }
  }, [mode, current, draftName, draftStyle, showFlash]);

  const handleSetDefault = useCallback(async () => {
    if (mode.kind !== "existing") return;
    setSaving(true);
    try {
      const updated = await api.updateSubtitlePreset(mode.presetId, {
        is_default: true,
      });
      setPresets((prev) =>
        prev.map((p) => ({
          ...p,
          is_default: p.id === updated.id,
        })),
      );
      showFlash("ok", `«${updated.name}» теперь применяется по умолчанию`);
    } catch (err) {
      showFlash("error", extractError(err));
    } finally {
      setSaving(false);
    }
  }, [mode, showFlash]);

  const handleDelete = useCallback(async () => {
    if (mode.kind !== "existing" || current === null) return;
    if (current.is_builtin) {
      showFlash(
        "error",
        "Встроенные пресеты защищены — создай на его основе свой и удаляй его",
      );
      return;
    }
    if (!window.confirm(`Удалить пресет «${current.name}»?`)) return;
    setSaving(true);
    try {
      await api.deleteSubtitlePreset(current.id);
      const remaining = presets.filter((p) => p.id !== current.id);
      setPresets(remaining);
      if (remaining[0]) {
        selectPreset(remaining[0]);
      } else {
        startNewPreset();
      }
      showFlash("ok", "Удалено");
    } catch (err) {
      showFlash("error", extractError(err));
    } finally {
      setSaving(false);
    }
  }, [mode, current, presets, selectPreset, startNewPreset, showFlash]);

  const canSave =
    mode.kind === "existing" && current !== null && !current.is_builtin;
  const canDelete =
    mode.kind === "existing" && current !== null && !current.is_builtin;

  const refreshFonts = useCallback(async () => {
    setRefreshingFonts(true);
    try {
      const fresh = await api.refreshFonts();
      setFontsState(fresh);
      showFlash("ok", `Найдено ${fresh.fonts.length} шрифтов`);
    } catch (err) {
      showFlash("error", extractError(err));
    } finally {
      setRefreshingFonts(false);
    }
  }, [showFlash]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
      <aside className="flex flex-col gap-2">
        <button
          type="button"
          onClick={startNewPreset}
          className={`rounded-lg border border-dashed px-3 py-2 text-left text-sm transition-colors ${
            mode.kind === "new"
              ? "border-[color:var(--accent-primary)] text-[color:var(--accent-primary-hover)]"
              : "border-[color:var(--border-default)] text-[color:var(--text-secondary)] hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
          }`}
        >
          + Новый пресет
        </button>
        <div className="flex flex-col gap-1">
          {presets.map((preset) => {
            const active =
              mode.kind === "existing" && mode.presetId === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => selectPreset(preset)}
                className={`flex flex-col gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  active
                    ? "bg-[color:var(--accent-primary-subtle)] text-[color:var(--accent-primary-hover)]"
                    : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-sunken)] hover:text-[color:var(--text-primary)]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{preset.name}</span>
                  <div className="flex gap-1">
                    {preset.is_default && (
                      <span className="rounded-full bg-[color:var(--accent-primary)] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-[color:var(--accent-on-primary)]">
                        по&nbsp;умолч.
                      </span>
                    )}
                    {preset.is_builtin && (
                      <span className="rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[color:var(--text-muted)]">
                        встроен.
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-[10px] text-[color:var(--text-muted)]">
                  {preset.style.font} · {preset.style.size}px · {preset.style.anchor}
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            disabled={mode.kind === "existing" && current?.is_builtin}
            className="min-w-0 flex-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)] disabled:opacity-60"
            placeholder="Название пресета"
          />
          <div className="flex flex-wrap gap-2">
            {mode.kind === "new" ? (
              <button
                type="button"
                onClick={handleCreate}
                disabled={saving}
                className="rounded-lg bg-[color:var(--accent-primary)] px-3 py-2 text-xs font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]"
              >
                Создать
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleUpdate}
                  disabled={!canSave || saving}
                  className="rounded-lg bg-[color:var(--accent-primary)] px-3 py-2 text-xs font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]"
                >
                  Сохранить
                </button>
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={saving}
                  className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
                >
                  Сохранить как…
                </button>
                {!current?.is_default && (
                  <button
                    type="button"
                    onClick={handleSetDefault}
                    disabled={saving}
                    className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
                  >
                    Применять по умолчанию
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={!canDelete || saving}
                  className="rounded-lg border border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 px-3 py-2 text-xs text-[color:var(--danger)] transition-colors hover:border-[color:var(--danger)]/40 disabled:opacity-40"
                >
                  Удалить
                </button>
              </>
            )}
          </div>
        </div>
        {flash && (
          <div
            role="status"
            className={`rounded-lg border px-3 py-2 text-xs ${
              flash.kind === "ok"
                ? "border-[color:var(--success)]/30 bg-[color:var(--success)]/10 text-[color:var(--success)]"
                : "border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10 text-[color:var(--danger)]"
            }`}
          >
            {flash.message}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] px-3 py-2 text-[11px] text-[color:var(--text-secondary)]">
          <span>
            {fontsState.source === "system" ? (
              <>
                <span className="font-mono font-semibold text-[color:var(--text-primary)]">
                  {fontsState.fonts.length}
                </span>{" "}
                установленных шрифтов
                {fontsState.scanned_at && (
                  <>
                    {" "}
                    · обновлено{" "}
                    <span className="font-mono text-[color:var(--text-muted)]">
                      {formatTimeAgo(fontsState.scanned_at)}
                    </span>
                  </>
                )}
              </>
            ) : (
              <span className="text-[color:var(--warning)]">
                Используется базовый список ({fontsState.fonts.length} шрифтов).
                Нажми «Обновить», чтобы просканировать компьютер.
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={refreshFonts}
            disabled={refreshingFonts}
            className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)] disabled:cursor-wait disabled:opacity-60"
          >
            {refreshingFonts ? "Сканируем… (до 6 сек)" : "Обновить шрифты"}
          </button>
        </div>

        <div className="surface-card p-4">
          <SubtitleStyleEditor
            value={draftStyle}
            onChange={setDraftStyle}
            fitMode={previewFitMode}
            onFitModeChange={setPreviewFitMode}
            aspect={previewAspect}
            onAspectChange={setPreviewAspect}
            fonts={fontsState.fonts}
            favourites={{ favourites, onToggle: toggleFavourite }}
          />
        </div>
      </div>

      <aside className="flex flex-col gap-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
          Как будет в рилсе
        </h3>
        <SubtitlePreview
          config={draftStyle}
          aspect={previewAspect}
          fitMode={previewFitMode}
          previewHeight={520}
          showSafeZones
          onDragPosition={(x, y) => {
            if (draftStyle.position_mode !== "free") return;
            setDraftStyle({ ...draftStyle, free_x_pct: x, free_y_pct: y });
          }}
        />
      </aside>
    </div>
  );
}

function formatTimeAgo(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const diffSec = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (diffSec < 60) return "только что";
    const diffMin = Math.round(diffSec / 60);
    if (diffMin < 60) return `${diffMin} мин назад`;
    const diffHours = Math.round(diffMin / 60);
    if (diffHours < 24) return `${diffHours} ч назад`;
    const diffDays = Math.round(diffHours / 24);
    return `${diffDays} д назад`;
  } catch {
    return iso;
  }
}

function extractError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "object" && err.detail !== null) {
      const detail = (err.detail as Record<string, unknown>).detail;
      if (typeof detail === "string") return detail;
    }
    return JSON.stringify(err.detail);
  }
  return String(err);
}
