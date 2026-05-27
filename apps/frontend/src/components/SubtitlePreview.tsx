
import { useCallback, useMemo, useRef } from "react";
import type { SubtitleStyleConfig } from "@/lib/api";

// Instagram Reels safe zones в пикселях 1080×1920 canvas'а. Значения
// синхронизированы с backend'ом (``subtitle_styles.INSTAGRAM_SAFE_ZONES_9_16``)
// — держим в одном месте на бэке и повторяем здесь для visual guide.
const IG_SAFE_ZONES = {
  top: 220,
  bottom: 440,
  left: 64,
  right: 144,
};

function scaleSafeZones(presetW: number, presetH: number) {
  const scaleH = presetH / 1920;
  const scaleW = presetW / 1080;
  const scale = Math.min(scaleH, scaleW) || 1;
  return {
    top: Math.round(IG_SAFE_ZONES.top * scale),
    bottom: Math.round(IG_SAFE_ZONES.bottom * scale),
    left: Math.round(IG_SAFE_ZONES.left * scale),
    right: Math.round(IG_SAFE_ZONES.right * scale),
  };
}

/**
 * Зеркалит backend-логику ``_wrap_into_lines`` — чтобы предпросмотр показывал
 * то же разбиение, что получит libass. Жадный перенос по словам с жёстким
 * соблюдением ``max_chars`` на каждой строке; хвост склеивается с последней
 * разрешённой строкой если слов больше, чем ``max_lines × max_chars``.
 */
function wrapPreview(
  text: string,
  mode: "chars" | "sentence" | "word",
  maxLines: number,
  maxChars: number,
): string {
  if (mode === "word" || maxLines <= 1) return text;
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return text;
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (word.length >= maxChars) {
      if (current) {
        lines.push(current);
        current = "";
      }
      lines.push(word);
      continue;
    }
    if (!current) {
      current = word;
    } else if (current.length + 1 + word.length <= maxChars) {
      current = `${current} ${word}`;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines - 1);
    const overflow = lines.slice(maxLines - 1).join(" ");
    return [...kept, overflow].join("\n");
  }
  return lines.join("\n");
}

/**
 * Pixel-accurate preview рендера сабов: принимает тот же SubtitleStyleConfig
 * что уходит на бэкенд, и воспроизводит результат libass через CSS.
 *
 * Маппинг (см. `services/subtitle_styles.py::resolve_style`):
 *   - `-webkit-text-stroke` ≈ ASS Outline
 *   - `text-shadow` ≈ ASS Shadow (при border_style=1)
 *   - `background + padding` ≈ ASS BorderStyle=3 (opaque box)
 *   - `margin_v + alignment` (anchor/bottom/top/center)
 *     пересчитываются тем же алгоритмом, что и в бэкенде.
 */

interface PresetDims {
  width: number;
  height: number;
}

const ASPECT_DIMS: Record<string, PresetDims> = {
  "9:16": { width: 1080, height: 1920 },
  "16:9": { width: 1920, height: 1080 },
  "1:1": { width: 1080, height: 1080 },
  "4:5": { width: 1080, height: 1350 },
};

// Классические source aspect'ы — для иллюстрации letterbox в fit-режиме.
// 9:16 target с 16:9 source даёт самый узнаваемый letterbox 656 px снизу/сверху.
const SIMULATED_SOURCE: Record<string, PresetDims> = {
  "9:16": { width: 1920, height: 1080 },
  "16:9": { width: 1080, height: 1920 },
  "1:1": { width: 1920, height: 1080 },
  "4:5": { width: 1920, height: 1080 },
};

interface LetterboxReal {
  scaledWidth: number;
  scaledHeight: number;
  letterboxTop: number;
  letterboxBottom: number;
  pillarLeft: number;
  pillarRight: number;
}

function computeLetterbox(
  presetW: number,
  presetH: number,
  fitMode: string,
  src: PresetDims | null,
): LetterboxReal {
  if (fitMode !== "fit" || src === null) {
    return {
      scaledWidth: presetW,
      scaledHeight: presetH,
      letterboxTop: 0,
      letterboxBottom: 0,
      pillarLeft: 0,
      pillarRight: 0,
    };
  }
  const scale = Math.min(presetW / src.width, presetH / src.height);
  const scaledW = Math.round(src.width * scale);
  const scaledH = Math.round(src.height * scale);
  const totalV = Math.max(0, presetH - scaledH);
  const totalH = Math.max(0, presetW - scaledW);
  return {
    scaledWidth: scaledW,
    scaledHeight: scaledH,
    letterboxTop: Math.floor(totalV / 2),
    letterboxBottom: totalV - Math.floor(totalV / 2),
    pillarLeft: Math.floor(totalH / 2),
    pillarRight: totalH - Math.floor(totalH / 2),
  };
}

function computeMargin(
  cfg: SubtitleStyleConfig,
  presetH: number,
  fitMode: string,
  letterbox: LetterboxReal,
): { alignment: "top" | "center" | "bottom"; marginPx: number } {
  const offset = Math.max(0, cfg.offset_px);
  if (cfg.anchor === "center") {
    if (fitMode === "fit" || offset === 0) {
      return { alignment: "center", marginPx: 0 };
    }
    return { alignment: "top", marginPx: presetH / 2 + offset };
  }
  if (fitMode === "fit") {
    const letter =
      cfg.anchor === "bottom" ? letterbox.letterboxBottom : letterbox.letterboxTop;
    return {
      alignment: cfg.anchor,
      marginPx: Math.max(0, letter - offset),
    };
  }
  return { alignment: cfg.anchor, marginPx: offset };
}

function hexToRgba(hex: string, opacityPercent: number): string {
  if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const a = Math.max(0, Math.min(100, opacityPercent)) / 100;
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function weightToCss(weight: string): number {
  if (weight === "bold") return 700;
  if (weight === "medium") return 500;
  return 400;
}

interface Props {
  config: SubtitleStyleConfig;
  aspect: string;
  fitMode: "fill" | "fit";
  /** Опциональное имитирование реального источника. По умолчанию — классические
   *  16:9 / 9:16 (в зависимости от target'а) для наглядности letterbox. */
  sourceAspect?: string | null;
  sampleText?: string;
  /** Высота preview в пикселях экрана. Ширина вычисляется от aspect. */
  previewHeight?: number;
  showAnchorGuide?: boolean;
  /** Показывать ли полупрозрачный overlay IG safe-zones поверх превью. */
  showSafeZones?: boolean;
  /** Callback при перетаскивании текста в free-режиме. Получает новые
   *  проценты X/Y относительно canvas'а. Если не задан — текст не тянется. */
  onDragPosition?: (freeXPct: number, freeYPct: number) => void;
}

export function SubtitlePreview({
  config,
  aspect,
  fitMode,
  sourceAspect,
  sampleText = "Когда говорю медленно — всё звучит как чеканная правда",
  previewHeight = 420,
  showAnchorGuide = true,
  showSafeZones = false,
  onDragPosition,
}: Props) {
  const preset = ASPECT_DIMS[aspect] ?? ASPECT_DIMS["9:16"];
  const src = sourceAspect
    ? (ASPECT_DIMS[sourceAspect] ?? null)
    : (SIMULATED_SOURCE[aspect] ?? null);

  const letterbox = useMemo(
    () => computeLetterbox(preset.width, preset.height, fitMode, src),
    [preset.width, preset.height, fitMode, src],
  );

  const margin = useMemo(
    () => computeMargin(config, preset.height, fitMode, letterbox),
    [config, preset.height, fitMode, letterbox],
  );

  const scale = previewHeight / preset.height;
  const previewWidth = Math.round(preset.width * scale);
  const fontSizePx = Math.max(6, Math.round(config.size * scale));
  const outlinePx = Math.max(0, config.outline_width * scale);
  const shadowDx = Math.round(config.shadow_width * scale);
  const shadowDy = Math.round(config.shadow_width * scale);

  const textColor = hexToRgba(config.primary_color, config.text_opacity);
  const shadowColor = hexToRgba(config.shadow_color, config.shadow_opacity);
  const outlineColor = config.outline_color;
  const bgColor = hexToRgba(config.background_color, config.background_opacity);

  // Пропорционально scale масштабируем padding, чтобы подложка выглядела
  // корректно относительно текста.
  const paddingPx = Math.max(1, Math.round(config.background_padding * scale));

  const textStyles: React.CSSProperties = {
    fontFamily: `'${config.font}', sans-serif`,
    fontSize: `${fontSizePx}px`,
    fontWeight: weightToCss(config.weight),
    fontStyle: config.italic ? "italic" : "normal",
    color: textColor,
    lineHeight: 1.2,
    textAlign: "center",
    whiteSpace: "pre-wrap",
    display: "inline-block",
    WebkitTextStroke:
      outlinePx > 0 ? `${outlinePx}px ${outlineColor}` : undefined,
    textShadow:
      config.shadow_width > 0 && !config.background
        ? `${shadowDx}px ${shadowDy}px ${shadowDy}px ${shadowColor}`
        : undefined,
    background: config.background ? bgColor : undefined,
    padding: config.background ? `${paddingPx}px ${paddingPx * 2}px` : undefined,
    borderRadius: config.background ? "2px" : undefined,
  };

  const safeZones = useMemo(
    () => scaleSafeZones(preset.width, preset.height),
    [preset.width, preset.height],
  );

  // Free-mode: clamp процентов в safe-zone если опция включена.
  const freeCenter = useMemo(() => {
    if (config.position_mode !== "free") return null;
    let x = (config.free_x_pct / 100) * preset.width;
    let y = (config.free_y_pct / 100) * preset.height;
    if (config.clamp_to_safe_zone) {
      x = Math.max(safeZones.left, Math.min(preset.width - safeZones.right, x));
      y = Math.max(safeZones.top, Math.min(preset.height - safeZones.bottom, y));
    }
    return { x, y };
  }, [
    config.position_mode,
    config.free_x_pct,
    config.free_y_pct,
    config.clamp_to_safe_zone,
    preset.width,
    preset.height,
    safeZones,
  ]);

  const positionStyles: React.CSSProperties = {
    position: "absolute",
    display: "flex",
    justifyContent: "center",
    pointerEvents: onDragPosition && config.position_mode === "free" ? "auto" : "none",
  };
  if (freeCenter) {
    positionStyles.left = `${freeCenter.x * scale}px`;
    positionStyles.top = `${freeCenter.y * scale}px`;
    positionStyles.transform = "translate(-50%, -50%)";
    positionStyles.cursor = onDragPosition ? "grab" : "default";
  } else if (margin.alignment === "bottom") {
    positionStyles.left = "0";
    positionStyles.right = "0";
    positionStyles.bottom = `${margin.marginPx * scale}px`;
  } else if (margin.alignment === "top") {
    positionStyles.left = "0";
    positionStyles.right = "0";
    positionStyles.top = `${margin.marginPx * scale}px`;
  } else {
    positionStyles.left = "0";
    positionStyles.right = "0";
    positionStyles.top = "50%";
    positionStyles.transform = "translateY(-50%)";
  }

  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<{ active: boolean } | null>(null);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLSpanElement>) => {
      if (!onDragPosition || config.position_mode !== "free") return;
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      dragState.current = { active: true };
      e.preventDefault();
    },
    [onDragPosition, config.position_mode],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLSpanElement>) => {
      if (!onDragPosition || !dragState.current?.active) return;
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const relX = e.clientX - rect.left;
      const relY = e.clientY - rect.top;
      const xPct = Math.max(0, Math.min(100, (relX / rect.width) * 100));
      const yPct = Math.max(0, Math.min(100, (relY / rect.height) * 100));
      onDragPosition(xPct, yPct);
    },
    [onDragPosition],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent<HTMLSpanElement>) => {
      if (dragState.current) {
        dragState.current.active = false;
      }
      (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
    },
    [],
  );

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-lg border border-[color:var(--border-default)] bg-gradient-to-br from-violet-700 via-purple-600 to-fuchsia-600 shadow-inner"
        style={{
          width: `${previewWidth}px`,
          height: `${previewHeight}px`,
        }}
        aria-label={`Предпросмотр субтитра — ${aspect} / ${fitMode}`}
      >
        {fitMode === "fit" && (letterbox.letterboxTop > 0 || letterbox.letterboxBottom > 0) && (
          <>
            <div
              className="absolute left-0 right-0 top-0 bg-black"
              style={{ height: `${letterbox.letterboxTop * scale}px` }}
            />
            <div
              className="absolute left-0 right-0 bottom-0 bg-black"
              style={{ height: `${letterbox.letterboxBottom * scale}px` }}
            />
          </>
        )}
        {fitMode === "fit" && (letterbox.pillarLeft > 0 || letterbox.pillarRight > 0) && (
          <>
            <div
              className="absolute top-0 bottom-0 left-0 bg-black"
              style={{ width: `${letterbox.pillarLeft * scale}px` }}
            />
            <div
              className="absolute top-0 bottom-0 right-0 bg-black"
              style={{ width: `${letterbox.pillarRight * scale}px` }}
            />
          </>
        )}

        {fitMode === "fit" && (
          <FitVideoFrame
            letterbox={letterbox}
            scale={scale}
            previewWidth={previewWidth}
            previewHeight={previewHeight}
          />
        )}

        {showAnchorGuide && config.position_mode === "anchor" && (
          <AnchorGuide
            anchor={config.anchor}
            marginPx={margin.marginPx}
            offset={config.offset_px}
            scale={scale}
            previewWidth={previewWidth}
            previewHeight={previewHeight}
            fitMode={fitMode}
            letterbox={letterbox}
          />
        )}

        {showSafeZones && (
          <SafeZoneOverlay
            safeZones={safeZones}
            scale={scale}
            previewWidth={previewWidth}
            previewHeight={previewHeight}
          />
        )}

        <div style={positionStyles}>
          <span
            style={textStyles}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          >
            {wrapPreview(
              sampleText,
              config.wrap_mode,
              config.max_lines,
              config.max_chars_per_line,
            )}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-[11px] text-[color:var(--text-muted)]">
        <span>
          Размер {preset.width}×{preset.height} · положение{" "}
          {margin.alignment === "top"
            ? "сверху"
            : margin.alignment === "bottom"
              ? "снизу"
              : "по центру"}{" "}
          · отступ {Math.round(margin.marginPx)} пикс
        </span>
        <span className="font-mono">
          {fitMode === "fit" && src
            ? `${src.width}×${src.height}, поля ${letterbox.letterboxTop}/${letterbox.letterboxBottom}`
            : "весь кадр"}
        </span>
      </div>
    </div>
  );
}

interface GuideProps {
  anchor: "top" | "center" | "bottom";
  marginPx: number;
  offset: number;
  scale: number;
  previewWidth: number;
  previewHeight: number;
  fitMode: "fill" | "fit";
  letterbox: LetterboxReal;
}

function AnchorGuide({
  anchor,
  marginPx,
  offset,
  scale,
  previewWidth,
  previewHeight,
  fitMode,
  letterbox,
}: GuideProps) {
  // Якорная линия (от края, куда MarginV отсчитывается).
  let anchorLineStyle: React.CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    height: "1px",
    borderTop: "1px dashed rgba(255,255,255,0.25)",
    pointerEvents: "none",
  };
  let anchorLabel = "";

  if (anchor === "bottom") {
    const baseFromBottom =
      fitMode === "fit" ? letterbox.letterboxBottom * scale : 0;
    anchorLineStyle.bottom = `${baseFromBottom}px`;
    anchorLabel =
      fitMode === "fit"
        ? `нижняя граница видео · смещение ${offset} пикс`
        : `нижний край кадра · смещение ${offset} пикс`;
  } else if (anchor === "top") {
    const baseFromTop =
      fitMode === "fit" ? letterbox.letterboxTop * scale : 0;
    anchorLineStyle.top = `${baseFromTop}px`;
    anchorLabel =
      fitMode === "fit"
        ? `верхняя граница видео · смещение ${offset} пикс`
        : `верхний край кадра · смещение ${offset} пикс`;
  } else {
    anchorLineStyle = {
      ...anchorLineStyle,
      top: "50%",
      transform: "translateY(-0.5px)",
    };
    anchorLabel =
      fitMode === "fit"
        ? "центр · смещение не применяется в этом режиме"
        : `центр кадра · смещение ${offset} пикс`;
  }

  return (
    <>
      <div style={anchorLineStyle} />
      <span
        className="absolute rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-white"
        style={{
          ...(anchor === "bottom"
            ? { bottom: "4px", left: "4px" }
            : anchor === "top"
              ? { top: "4px", left: "4px" }
              : { top: "calc(50% + 4px)", left: "4px" }),
        }}
      >
        {anchorLabel}
      </span>
      <span className="sr-only">
        preview geometry: {previewWidth}×{previewHeight}, marginV={Math.round(
          marginPx,
        )}
      </span>
    </>
  );
}

interface FitFrameProps {
  letterbox: LetterboxReal;
  scale: number;
  previewWidth: number;
  previewHeight: number;
}

function FitVideoFrame({ letterbox, scale, previewWidth, previewHeight }: FitFrameProps) {
  const frameTop = letterbox.letterboxTop * scale;
  const frameLeft = letterbox.pillarLeft * scale;
  const frameW = letterbox.scaledWidth * scale;
  const frameH = letterbox.scaledHeight * scale;
  if (frameW <= 0 || frameH <= 0) return null;
  return (
    <>
      <div
        className="absolute pointer-events-none"
        style={{
          left: `${frameLeft}px`,
          top: `${frameTop}px`,
          width: `${frameW}px`,
          height: `${frameH}px`,
          border: "1px dashed rgba(56, 189, 248, 0.85)",
          boxShadow: "0 0 0 1px rgba(15, 23, 42, 0.55) inset",
        }}
        aria-hidden="true"
      />
      <span
        className="absolute rounded bg-sky-500/85 px-1.5 py-0.5 font-mono text-[9px] text-white"
        style={{
          left: `${frameLeft + 4}px`,
          top: `${frameTop + 4}px`,
          pointerEvents: "none",
        }}
      >
        видео · {Math.round(letterbox.scaledWidth)}×{Math.round(letterbox.scaledHeight)}
      </span>
      <span className="sr-only">
        preview geometry: {previewWidth}×{previewHeight}
      </span>
    </>
  );
}

interface SafeZoneProps {
  safeZones: { top: number; bottom: number; left: number; right: number };
  scale: number;
  previewWidth: number;
  previewHeight: number;
}

function SafeZoneOverlay({ safeZones, scale, previewWidth, previewHeight }: SafeZoneProps) {
  const topPx = safeZones.top * scale;
  const bottomPx = safeZones.bottom * scale;
  const leftPx = safeZones.left * scale;
  const rightPx = safeZones.right * scale;
  const stripeBg = "rgba(239, 68, 68, 0.22)";
  const borderColor = "rgba(239, 68, 68, 0.7)";
  return (
    <>
      <div
        className="absolute left-0 right-0 top-0 pointer-events-none"
        style={{ height: `${topPx}px`, background: stripeBg, borderBottom: `1px dashed ${borderColor}` }}
        aria-hidden="true"
      />
      <div
        className="absolute left-0 right-0 bottom-0 pointer-events-none"
        style={{ height: `${bottomPx}px`, background: stripeBg, borderTop: `1px dashed ${borderColor}` }}
        aria-hidden="true"
      />
      <div
        className="absolute top-0 bottom-0 left-0 pointer-events-none"
        style={{ width: `${leftPx}px`, background: stripeBg, borderRight: `1px dashed ${borderColor}` }}
        aria-hidden="true"
      />
      <div
        className="absolute top-0 bottom-0 right-0 pointer-events-none"
        style={{ width: `${rightPx}px`, background: stripeBg, borderLeft: `1px dashed ${borderColor}` }}
        aria-hidden="true"
      />
      <span
        className="absolute right-1 top-1 rounded bg-[color:var(--danger)]/80 px-1.5 py-0.5 font-mono text-[9px] text-white"
        style={{ pointerEvents: "none" }}
      >
        IG safe zones · {previewWidth}×{previewHeight}
      </span>
    </>
  );
}
