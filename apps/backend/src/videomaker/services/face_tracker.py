"""Face detection через mediapipe для face-tracked zoom.

Стратегия:
* Sampling — 1 кадр каждые `sample_interval_sec` (default 2.0). Для 60-минутного
  видео это 1800 кадров, ~1 минута wall-time на M-series CPU.
* Кэш на диске по SHA256 видеофайла → `data/face_cache/<sha256>.json`. Повторный
  zoom-pass с изменённой конфигурацией пресета НЕ пересчитывает faces.
* mediapipe Tasks API (`mediapipe.tasks.python.vision.FaceDetector`) с моделью
  `blaze_face_short_range.tflite` — auto-download при первом запуске в
  `data/models/` (~230 KiB).
* Frame extraction через ffmpeg `-vf fps=1/N` — без opencv VideoCapture, без
  fallback на full-frame decode.

Координаты bbox **нормализованы** (0..1) относительно кадра — переносится
между разрешениями. `FaceBBox.eyes_y` = `y + h*0.4` (анатомически глаза
расположены примерно на 40% сверху bbox лица) — используется как anchor для
zoom_planner.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing as mp
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from videomaker.core.logging import get_logger
from videomaker.services.media import probe
from videomaker.services.subprocess_utils import communicate_with_timeout

# Float16 модель — баланс точности и размера. Short range для лиц ≤ 2m
# (фронтальные интервью). URL стабилен и публичен на storage.googleapis.com.
FACE_DETECTOR_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
FACE_DETECTOR_MODEL_FILENAME = "blaze_face_short_range.tflite"
_MODEL_DOWNLOAD_TIMEOUT_SEC = 30.0

log = get_logger(__name__)

CACHE_VERSION = 1
_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(slots=True)
class FaceBBox:
    """Нормализованные координаты лица в кадре (0..1)."""

    x: float
    y: float
    w: float
    h: float
    confidence: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def eyes_y(self) -> float:
        """Анатомически глаза ≈ 40% от верхнего края bbox лица."""
        return self.y + self.h * 0.4

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(slots=True)
class FrameDetection:
    timestamp_sec: float
    faces: list[FaceBBox] = field(default_factory=list)

    @property
    def primary_face(self) -> FaceBBox | None:
        """Лицо с наибольшей площадью (предполагаемо ближайшее к камере)."""

        if not self.faces:
            return None
        return max(self.faces, key=lambda f: f.area)


@dataclass(slots=True)
class FaceTrackResult:
    video_path: str
    video_hash: str
    sample_interval_sec: float
    frame_width: int
    frame_height: int
    detections: list[FrameDetection]

    def best_face_at(self, t_sec: float) -> FaceBBox | None:
        """Возвращает interpolated bbox для момента `t_sec`.

        Логика:
        1. Находим левого и правого соседа в `detections` относительно `t_sec`.
        2. Если ОБА имеют primary_face — линейная interpolation
           (weighted average) по времени. Smoothing между sampled frames.
        3. Если только один — возвращаем его primary_face.
        4. Если ни один из ближайших — расширяем поиск ±2 sample на каждую сторону.
        5. Иначе None.

        Smoothing предотвращает ступенчатые скачки anchor между двумя
        sampled frames (полезно для длинных сегментов с движением спикера).
        """

        if not self.detections:
            return None

        # Находим левого и правого соседа
        left_idx = -1
        right_idx = -1
        for i, det in enumerate(self.detections):
            if det.timestamp_sec <= t_sec:
                left_idx = i
            else:
                right_idx = i
                break

        left = self.detections[left_idx] if left_idx >= 0 else None
        right = self.detections[right_idx] if right_idx >= 0 else None

        left_face = left.primary_face if left else None
        right_face = right.primary_face if right else None

        # Оба соседа имеют лицо — линейная интерполяция weighted by time distance
        if left_face is not None and right_face is not None and left and right:
            span = right.timestamp_sec - left.timestamp_sec
            if span <= 0:
                return left_face
            w_right = (t_sec - left.timestamp_sec) / span
            w_left = 1.0 - w_right
            return FaceBBox(
                x=left_face.x * w_left + right_face.x * w_right,
                y=left_face.y * w_left + right_face.y * w_right,
                w=left_face.w * w_left + right_face.w * w_right,
                h=left_face.h * w_left + right_face.h * w_right,
                confidence=min(left_face.confidence, right_face.confidence),
            )

        # Только один сосед имеет лицо
        if left_face is not None:
            return left_face
        if right_face is not None:
            return right_face

        # Расширенный поиск ±2 sample на каждую сторону
        anchor_idx = left_idx if left_idx >= 0 else right_idx
        if anchor_idx < 0:
            return None
        for offset in range(1, 3):
            for direction in (-1, 1):
                idx = anchor_idx + direction * offset
                if 0 <= idx < len(self.detections):
                    candidate = self.detections[idx].primary_face
                    if candidate is not None:
                        return candidate
        return None

    def to_json(self) -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "video_path": self.video_path,
            "video_hash": self.video_hash,
            "sample_interval_sec": self.sample_interval_sec,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "detections": [
                {
                    "timestamp_sec": d.timestamp_sec,
                    "faces": [asdict(f) for f in d.faces],
                }
                for d in self.detections
            ],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FaceTrackResult:
        if data.get("version") != CACHE_VERSION:
            raise FaceTrackerError(
                f"face cache version mismatch: expected {CACHE_VERSION}, got {data.get('version')}"
            )
        return cls(
            video_path=data["video_path"],
            video_hash=data["video_hash"],
            sample_interval_sec=float(data["sample_interval_sec"]),
            frame_width=int(data["frame_width"]),
            frame_height=int(data["frame_height"]),
            detections=[
                FrameDetection(
                    timestamp_sec=float(d["timestamp_sec"]),
                    faces=[FaceBBox(**f) for f in d["faces"]],
                )
                for d in data["detections"]
            ],
        )


class FaceTrackerError(RuntimeError):
    pass


async def track_faces(
    *,
    video_path: Path,
    sample_interval_sec: float = 1.5,
    cache_dir: Path | None = None,
    models_dir: Path,
    min_confidence: float = 0.5,
    timeout_sec: float = 600.0,
    force_refresh: bool = False,
) -> FaceTrackResult:
    """Запускает face detection на видео и возвращает результат.

    Args:
        video_path: путь к видео.
        sample_interval_sec: интервал между sampled кадрами (default 2.0).
        cache_dir: куда писать кэш. Если None — кэш не используется.
        models_dir: каталог для tflite-модели mediapipe. Auto-download при
            первом запуске. Обычно `settings.app_models_dir`.
        min_confidence: порог уверенности mediapipe (default 0.5).
        timeout_sec: hard-таймаут детекта в subprocess. При превышении процесс
            убивается и поднимается FaceTrackerError (фолбэк на center-crop).
        force_refresh: игнорировать кэш и пересчитать.
    """

    if not video_path.exists():
        raise FaceTrackerError(f"video file not found: {video_path}")
    if sample_interval_sec <= 0:
        raise FaceTrackerError(f"sample_interval_sec must be > 0, got {sample_interval_sec}")

    info = await probe(video_path)
    video_hash = await _hash_file_sha256(video_path)

    cache_path = (
        cache_dir / f"{video_hash}__{sample_interval_sec:.2f}s.json"
        if cache_dir is not None
        else None
    )

    if cache_path is not None and cache_path.exists() and not force_refresh:
        try:
            cached = FaceTrackResult.from_json(json.loads(cache_path.read_text(encoding="utf-8")))
            log.info(
                "face_track_cache_hit",
                video_hash=video_hash[:12],
                detections=len(cached.detections),
            )
            return cached
        except (FaceTrackerError, json.JSONDecodeError, KeyError) as exc:
            log.warning(
                "face_track_cache_invalid",
                video_hash=video_hash[:12],
                error=str(exc),
            )

    model_path = await ensure_model(models_dir)

    log.info(
        "face_track_start",
        video_hash=video_hash[:12],
        duration_sec=round(info.duration_sec, 1),
        sample_interval_sec=sample_interval_sec,
        timeout_sec=timeout_sec,
    )
    tmp_dir = Path(tempfile.mkdtemp(prefix="face_track_"))
    try:
        frames = await _extract_frames(video_path, sample_interval_sec, tmp_dir)
        # Process-изоляция: mediapipe гоняется в отдельном процессе с hard-kill.
        # asyncio.to_thread непрерываем — зависший mediapipe держал бы worker
        # вечно (job 8a418e9b). Subprocess убиваем по таймауту.
        detections = await _detect_faces_in_subprocess(
            frames,
            sample_interval_sec,
            min_confidence,
            model_path,
            timeout_sec,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    result = FaceTrackResult(
        video_path=str(video_path),
        video_hash=video_hash,
        sample_interval_sec=sample_interval_sec,
        frame_width=info.width,
        frame_height=info.height,
        detections=detections,
    )

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(result.to_json()), encoding="utf-8")
        tmp_path.replace(cache_path)
        log.info(
            "face_track_cache_written",
            video_hash=video_hash[:12],
            path=str(cache_path),
        )

    log.info(
        "face_track_done",
        video_hash=video_hash[:12],
        frames_sampled=len(detections),
        frames_with_face=sum(1 for d in detections if d.faces),
    )
    return result


async def _extract_frames(
    video_path: Path,
    sample_interval_sec: float,
    tmp_dir: Path,
) -> list[Path]:
    """Извлекает sampled кадры через async ffmpeg в переданный tmp_dir."""

    fps = 1.0 / sample_interval_sec
    frame_pattern = tmp_dir / "frame_%06d.png"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps:.6f}",
        "-vsync",
        "vfr",
        str(frame_pattern),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr_bytes = await communicate_with_timeout(proc)
    if proc.returncode != 0:
        raise FaceTrackerError(
            f"ffmpeg frame extraction failed (rc={proc.returncode}): "
            f"{stderr_bytes.decode(errors='replace')[:500]}"
        )
    return sorted(tmp_dir.glob("frame_*.png"))


def _detect_faces_in_frames(
    frames: list[Path],
    sample_interval_sec: float,
    min_confidence: float,
    model_path: Path,
) -> list[FrameDetection]:
    """Прогоняет mediapipe Tasks API по готовому списку кадров.

    Sync-функция — mediapipe блокирующий. Запускается через asyncio.to_thread
    из родительского async-контекста; ffmpeg-extraction и cleanup живут в
    async-части, чтобы не держать thread-pool worker на subprocess-ожидании.
    """

    if not frames:
        return []

    import mediapipe as mp  # type: ignore[import-untyped]
    from mediapipe.tasks import python as mp_python  # type: ignore[import-untyped]
    from mediapipe.tasks.python import vision as mp_vision  # type: ignore[import-untyped]

    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = mp_vision.FaceDetectorOptions(
        base_options=base_options,
        min_detection_confidence=min_confidence,
    )

    detections: list[FrameDetection] = []
    with mp_vision.FaceDetector.create_from_options(options) as detector:
        for idx, frame_path in enumerate(frames):
            # Timestamp кадра: первый кадр взят на t=0, далее с шагом interval.
            timestamp = idx * sample_interval_sec
            mp_image = mp.Image.create_from_file(str(frame_path))
            detection = detector.detect(mp_image)
            frame_w = mp_image.width
            frame_h = mp_image.height
            faces: list[FaceBBox] = []
            for det in detection.detections:
                bb = det.bounding_box
                confidence = (
                    float(det.categories[0].score)
                    if det.categories
                    else 0.0
                )
                faces.append(
                    FaceBBox(
                        x=float(max(0.0, min(1.0, bb.origin_x / frame_w))),
                        y=float(max(0.0, min(1.0, bb.origin_y / frame_h))),
                        w=float(max(0.0, min(1.0, bb.width / frame_w))),
                        h=float(max(0.0, min(1.0, bb.height / frame_h))),
                        confidence=confidence,
                    )
                )
            detections.append(
                FrameDetection(timestamp_sec=timestamp, faces=faces)
            )

    return detections


def _detect_faces_worker(
    queue: mp.Queue[tuple[bool, Any]],
    frames: list[Path],
    sample_interval_sec: float,
    min_confidence: float,
    model_path: Path,
) -> None:
    """Process-entrypoint: гоняет mediapipe-детект и кладёт результат в queue.

    Должна быть module-level (picklable для spawn). При успехе кладёт
    ``(True, detections)``, при исключении — ``(False, repr(exc))``. Сам процесс
    живёт изолированно: при hang родитель его убивает (terminate/kill), не
    дожидаясь — thread-pool worker родителя не блокируется.
    """

    try:
        detections = _detect_faces_in_frames(
            frames, sample_interval_sec, min_confidence, model_path
        )
        queue.put((True, detections))
    except BaseException as exc:
        queue.put((False, repr(exc)))


async def _detect_faces_in_subprocess(
    frames: list[Path],
    sample_interval_sec: float,
    min_confidence: float,
    model_path: Path,
    timeout_sec: float,
) -> list[FrameDetection]:
    """Запускает mediapipe-детект в отдельном ПРОЦЕССЕ с hard-таймаутом и kill.

    ``asyncio.to_thread`` непрерываем: зависший sync mediapipe держит worker
    вечно (job 8a418e9b). Процесс же убиваем — terminate(), затем kill() если
    не отвечает. При таймауте/краше процесса/ошибке внутри — поднимаем
    ``FaceTrackerError``, который ловит фолбэк-путь рендера (center-crop).
    """

    if not frames:
        return []

    ctx = mp.get_context("spawn")
    queue: mp.Queue[tuple[bool, Any]] = ctx.Queue()
    proc = ctx.Process(
        target=_detect_faces_worker,
        args=(queue, frames, sample_interval_sec, min_confidence, model_path),
        daemon=True,
    )
    proc.start()

    def _kill_process() -> None:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5.0)

    try:
        # Ожидаем готовности queue в thread-pool, но с hard-таймаутом на уровне
        # asyncio — даже если get() висит, мы выходим и убиваем процесс.
        ok, payload = await asyncio.wait_for(
            asyncio.to_thread(queue.get),
            timeout=timeout_sec,
        )
    except TimeoutError as exc:
        await asyncio.to_thread(_kill_process)
        log.warning(
            "face_track_timeout_killed",
            timeout_sec=timeout_sec,
            frames=len(frames),
        )
        raise FaceTrackerError(
            f"mediapipe detect timed out after {timeout_sec}s, process killed"
        ) from exc
    finally:
        # Подчищаем процесс в любом исходе (успех/ошибка), чтобы не оставить
        # зомби и освободить queue-feeder thread.
        await asyncio.to_thread(_kill_process)
        queue.close()

    if not ok:
        raise FaceTrackerError(f"mediapipe detect failed in subprocess: {payload}")
    return payload


async def ensure_model(models_dir: Path) -> Path:
    """Гарантирует наличие tflite-модели, скачивая при первом запуске.

    Используется единый путь `<models_dir>/blaze_face_short_range.tflite`.
    Скачивание идёт через `urllib` в отдельном потоке (asyncio.to_thread),
    атомарно через `.tmp` + `.replace`.
    """

    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / FACE_DETECTOR_MODEL_FILENAME
    if model_path.exists() and model_path.stat().st_size > 0:
        return model_path

    log.info("face_detector_model_download_start", url=FACE_DETECTOR_MODEL_URL)
    tmp_path = model_path.with_suffix(".tflite.tmp")

    def _download() -> None:
        # Defence-in-depth: file://, ftp:// и прочие не-HTTP схемы запрещены,
        # даже если URL контролируется только этим модулем. Защита от
        # случайного изменения константы на вредоносный путь / LFI через env.
        parsed = urlparse(FACE_DETECTOR_MODEL_URL)
        if parsed.scheme not in ("http", "https"):
            raise FaceTrackerError(
                f"unsupported URL scheme: {parsed.scheme!r} (expected http/https)"
            )
        try:
            with urllib.request.urlopen(
                FACE_DETECTOR_MODEL_URL, timeout=_MODEL_DOWNLOAD_TIMEOUT_SEC
            ) as response, tmp_path.open("wb") as fh:
                while chunk := response.read(64 * 1024):
                    fh.write(chunk)
        except (urllib.error.URLError, TimeoutError) as exc:
            tmp_path.unlink(missing_ok=True)
            raise FaceTrackerError(
                f"failed to download face detector model from "
                f"{FACE_DETECTOR_MODEL_URL}: {exc}"
            ) from exc

    await asyncio.to_thread(_download)

    if not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise FaceTrackerError("downloaded model file is empty")

    tmp_path.replace(model_path)
    log.info(
        "face_detector_model_ready",
        path=str(model_path),
        size_kb=round(model_path.stat().st_size / 1024, 1),
    )
    return model_path


async def _hash_file_sha256(path: Path) -> str:
    def _compute() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    return await asyncio.to_thread(_compute)


def cleanup_cache(cache_dir: Path) -> int:
    """Удаляет всё содержимое face cache. Возвращает количество удалённых файлов."""

    if not cache_dir.exists():
        return 0
    count = 0
    for entry in cache_dir.iterdir():
        if entry.is_file() and entry.suffix == ".json":
            entry.unlink()
            count += 1
    return count


__all__ = [
    "CACHE_VERSION",
    "FaceBBox",
    "FaceTrackResult",
    "FaceTrackerError",
    "FrameDetection",
    "cleanup_cache",
    "track_faces",
]
