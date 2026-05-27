
import { useCallback, useMemo, useRef, useState } from "react";
import type { SplitScreenConfig, SplitScreenTransform } from "@/lib/api";

const CANVAS_W = 1080;
const CANVAS_H = 1920;

type PanelKey = "main" | "companion";

interface DraggingState {
  panel: PanelKey;
  kind: "move" | "resize";
  startX: number;
  startY: number;
  startRect: SplitScreenTransform;
}

interface PanelProps {
  panelKey: PanelKey;
  transform: SplitScreenTransform;
  imageUrl: string | null;
  label: string;
  editable: boolean;
  onMoveStart: (panelKey: PanelKey, e: React.PointerEvent) => void;
  onResizeStart: (panelKey: PanelKey, e: React.PointerEvent) => void;
}

function Panel({
  panelKey,
  transform,
  imageUrl,
  label,
  editable,
  onMoveStart,
  onResizeStart,
}: PanelProps) {
  const { x_pct, y_pct, width_pct, height_pct } = transform;

  return (
    <div
      style={{
        position: "absolute",
        left: `${x_pct}%`,
        top: `${y_pct}%`,
        width: `${width_pct}%`,
        height: `${height_pct}%`,
        overflow: "hidden",
        border: "1px dashed rgba(255,255,255,0.4)",
        boxSizing: "border-box",
        cursor: editable ? "grab" : "default",
      }}
      onPointerDown={
        editable
          ? (e) => {
              onMoveStart(panelKey, e);
            }
          : undefined
      }
    >
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={label}
          draggable={false}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
            userSelect: "none",
            pointerEvents: "none",
          }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(30,30,30,0.8)",
            color: "rgba(255,255,255,0.4)",
            fontSize: 11,
            fontFamily: "monospace",
            textAlign: "center",
            padding: "0 8px",
          }}
        >
          {label} — кадр недоступен
        </div>
      )}

      {/* Label pill */}
      <div
        style={{
          position: "absolute",
          top: 4,
          left: 4,
          background: "rgba(0,0,0,0.7)",
          color: "#fff",
          fontSize: 10,
          fontFamily: "monospace",
          padding: "2px 6px",
          borderRadius: 4,
          pointerEvents: "none",
          userSelect: "none",
        }}
      >
        {label}
      </div>

      {/* Resize handle */}
      {editable && (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            right: 0,
            width: 16,
            height: 16,
            background: "rgba(255,255,255,0.8)",
            cursor: "nwse-resize",
            borderTopLeftRadius: 3,
          }}
          onPointerDown={(e) => {
            e.stopPropagation();
            onResizeStart(panelKey, e);
          }}
        />
      )}
    </div>
  );
}

interface Props {
  config: SplitScreenConfig;
  sourceThumbUrl: string | null;
  companionThumbUrl: string | null;
  previewHeight?: number;
  onChange: (next: SplitScreenConfig) => void;
}

export function SplitScreenPreviewEditor({
  config,
  sourceThumbUrl,
  companionThumbUrl,
  previewHeight = 520,
  onChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<DraggingState | null>(null);

  const previewWidth = Math.round((previewHeight * CANVAS_W) / CANVAS_H);

  const {
    main_fit_mode,
    companion_fit_mode,
    split_ratio,
    main_transform,
    companion_transform,
  } = config;

  const mainEditable = main_fit_mode === "manual";
  const companionEditable = companion_fit_mode === "manual";

  const effectiveTransforms = useMemo<{
    main: SplitScreenTransform;
    companion: SplitScreenTransform;
  }>(() => {
    const defaultMain: SplitScreenTransform = {
      x_pct: 0,
      y_pct: 0,
      width_pct: 100,
      height_pct: split_ratio,
    };
    const defaultCompanion: SplitScreenTransform = {
      x_pct: 0,
      y_pct: split_ratio,
      width_pct: 100,
      height_pct: 100 - split_ratio,
    };
    return {
      main: mainEditable ? main_transform : defaultMain,
      companion: companionEditable ? companion_transform : defaultCompanion,
    };
  }, [
    mainEditable,
    companionEditable,
    split_ratio,
    main_transform,
    companion_transform,
  ]);

  const handlePointerDown = useCallback(
    (panel: PanelKey, kind: "move" | "resize", e: React.PointerEvent) => {
      const editable =
        panel === "main" ? mainEditable : companionEditable;
      if (!editable) return;
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      const startRect =
        panel === "main"
          ? { ...config.main_transform }
          : { ...config.companion_transform };
      setDragging({
        panel,
        kind,
        startX: e.clientX,
        startY: e.clientY,
        startRect,
      });
    },
    [config, mainEditable, companionEditable],
  );

  const handleMoveStart = useCallback(
    (panel: PanelKey, e: React.PointerEvent) => {
      handlePointerDown(panel, "move", e);
    },
    [handlePointerDown],
  );

  const handleResizeStart = useCallback(
    (panel: PanelKey, e: React.PointerEvent) => {
      handlePointerDown(panel, "resize", e);
    },
    [handlePointerDown],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const dxPct = ((e.clientX - dragging.startX) / rect.width) * 100;
      const dyPct = ((e.clientY - dragging.startY) / rect.height) * 100;

      let next: SplitScreenTransform;

      if (dragging.kind === "move") {
        const { startRect } = dragging;
        const x_pct = Math.max(
          0,
          Math.min(100 - startRect.width_pct, startRect.x_pct + dxPct),
        );
        const y_pct = Math.max(
          0,
          Math.min(100 - startRect.height_pct, startRect.y_pct + dyPct),
        );
        next = {
          x_pct,
          y_pct,
          width_pct: startRect.width_pct,
          height_pct: startRect.height_pct,
        };
      } else {
        const { startRect } = dragging;
        const width_pct = Math.max(
          5,
          Math.min(100 - startRect.x_pct, startRect.width_pct + dxPct),
        );
        const height_pct = Math.max(
          5,
          Math.min(100 - startRect.y_pct, startRect.height_pct + dyPct),
        );
        next = {
          x_pct: startRect.x_pct,
          y_pct: startRect.y_pct,
          width_pct,
          height_pct,
        };
      }

      if (dragging.panel === "main") {
        onChange({ ...config, main_transform: next });
      } else {
        onChange({ ...config, companion_transform: next });
      }
    },
    [dragging, config, onChange],
  );

  const handlePointerUp = useCallback(() => {
    setDragging(null);
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: previewWidth,
        height: previewHeight,
        background: "#000",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.12)",
        overflow: "hidden",
        touchAction: "none",
        userSelect: "none",
      }}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <Panel
        panelKey="main"
        transform={effectiveTransforms.main}
        imageUrl={sourceThumbUrl}
        label="main"
        editable={mainEditable}
        onMoveStart={handleMoveStart}
        onResizeStart={handleResizeStart}
      />
      <Panel
        panelKey="companion"
        transform={effectiveTransforms.companion}
        imageUrl={companionThumbUrl}
        label="companion"
        editable={companionEditable}
        onMoveStart={handleMoveStart}
        onResizeStart={handleResizeStart}
      />
    </div>
  );
}
