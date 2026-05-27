"""T2.8 slice 1 — cursor detector через OpenCV template matching.

Эвристика: ищем курсор в каждом 30fps frame через matchTemplate с
набором эталонных sprites (macOS / Windows / Linux). Confidence > 0.3
на >=40% frames → считаем это скринкаст и возвращаем events. Иначе
graceful degrade — [], profile=screencast рендерится без cursor zoom.

Sprite files ожидаются в data/cursor_templates/*.png (32x32 BGRA).
Если папка пустая — возвращаем [].
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class CursorEvent:
    """Один отсемплированный кадр с найденным курсором."""

    x: int
    y: int
    t_sec: float
    confidence: float


async def detect_cursor_events(
    video_path: Path,
    sample_rate_hz: int = 30,
    templates_dir: Path | None = None,
) -> list[CursorEvent]:
    """Template matching cursor detection. Graceful degrade на [].

    - Если templates_dir пустой или не существует — возвращаем [].
    - Если opencv недоступен — возвращаем [] (graceful).
    - Если <40% frames имеют confidence > 0.3 — возвращаем []
      (вероятно, не скринкаст).
    """
    try:
        import cv2

        if templates_dir is None:
            templates_dir = (
                Path(__file__).resolve().parents[3]
                / "data"
                / "cursor_templates"
            )
        if not templates_dir.is_dir():
            log.info("cursor_templates_not_found", path=str(templates_dir))
            return []
        template_paths = sorted(templates_dir.glob("*.png"))
        if not template_paths:
            return []

        templates: list[tuple[str, Any]] = []
        for p in template_paths:
            tpl = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if tpl is None:
                continue
            if tpl.ndim == 3 and tpl.shape[2] >= 3:
                tpl_gray = cv2.cvtColor(tpl[:, :, :3], cv2.COLOR_BGR2GRAY)
            else:
                tpl_gray = tpl
            templates.append((p.name, tpl_gray))
        if not templates:
            return []

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            cap.release()
            return []
        stride = max(1, round(fps / max(1, sample_rate_hz)))

        events: list[CursorEvent] = []
        total_sampled = 0
        high_conf_count = 0
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % stride == 0:
                total_sampled += 1
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                best_conf = 0.0
                best_loc: tuple[int, int] | None = None
                best_size: tuple[int, int] = (0, 0)
                for _name, tpl_gray in templates:
                    if (
                        tpl_gray.shape[0] >= gray.shape[0]
                        or tpl_gray.shape[1] >= gray.shape[1]
                    ):
                        continue
                    res = cv2.matchTemplate(
                        gray, tpl_gray, cv2.TM_CCOEFF_NORMED
                    )
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if float(max_val) > best_conf:
                        best_conf = float(max_val)
                        best_loc = (int(max_loc[0]), int(max_loc[1]))
                        best_size = (
                            int(tpl_gray.shape[0]),
                            int(tpl_gray.shape[1]),
                        )
                if best_conf > 0.3 and best_loc is not None:
                    high_conf_count += 1
                    events.append(
                        CursorEvent(
                            x=best_loc[0] + best_size[1] // 2,
                            y=best_loc[1] + best_size[0] // 2,
                            t_sec=frame_idx / fps,
                            confidence=best_conf,
                        )
                    )
            frame_idx += 1
        cap.release()

        if total_sampled == 0 or high_conf_count / total_sampled < 0.4:
            log.info(
                "cursor_not_detected_reliably",
                sampled=total_sampled,
                high_conf=high_conf_count,
            )
            return []
        log.info(
            "cursor_detected",
            events=len(events),
            high_conf_ratio=round(high_conf_count / total_sampled, 3),
        )
        return events
    except Exception as exc:
        log.warning("cursor_detect_failed", error=str(exc))
        return []
