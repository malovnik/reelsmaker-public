"""Person clustering для fashion/travel профилей.

Группирует `FrameDetection` в кластеры "непрерывных шотов одного человека"
через temporal + spatial proximity. Не требует модели распознавания — работает
поверх существующего ``face_tracker`` bbox-output-а.

## Алгоритм

Greedy temporal clustering:

1. Пройдёмся по `detections` в порядке времени.
2. Для каждого `FrameDetection.primary_face` ищем активный кластер, у
   которого:
   * timestamp последней детекции `< t_current - MAX_GAP_SEC` → считается
     "закрытым", не расширяется
   * IoU с последним bbox активного кластера `>= IOU_THRESHOLD` → расширяем
3. Если подходящий кластер найден — добавляем frame туда, иначе создаём новый.

## Ограничения (осознанные)

* **Shot-level, не identity-level**: кластер = "непрерывный шот конкретного
  человека". Один и тот же человек в разных локациях = два разных кластера
  (bbox прыгает, сцена меняется).
* Для cross-scene identity clustering нужна модель face recognition
  (face_recognition / insightface / DLib). В videomaker она не интегрирована —
  это отдельная фаза (см. roadmap 3.2+).
* Fashion профиль использует кластеры как "кандидаты для склеек": выбираем
  крупные по duration кластеры с похожей bbox-геометрией (proxy для "тот же
  ракурс"). Это не идеал, но работает для многих fashion сцен где человек
  в одной композиции.

## Публичные функции

* ``cluster_persons(face_track_result)`` — список ``PersonCluster``
* ``PersonCluster.duration_sec`` — длительность шота
* ``PersonCluster.iou_with(other)`` — средняя bbox-геометрическая похожесть
  между центроидами (используется fashion ranker для multi-location candidates)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videomaker.core.logging import get_logger
from videomaker.services.face_tracker import FaceBBox, FaceTrackResult, FrameDetection

log = get_logger(__name__)

# Максимальный разрыв во времени, при котором всё ещё считаем что это один
# непрерывный шот. Больший разрыв — человек ушёл/сменилась сцена.
MAX_GAP_SEC = 2.0

# IoU порог для слияния смежных bbox в один шот. 0.3 — мягкий (учитывает
# движение), 0.5 — жёсткий.
IOU_THRESHOLD = 0.30

# Минимальная duration_sec чтобы кластер считался "значимым" (0.5s = 12-15
# кадров на 24-30 fps).
MIN_DURATION_SEC = 0.5


def _iou(a: FaceBBox, b: FaceBBox) -> float:
    """Intersection-over-Union двух bbox-ов в нормализованных координатах."""
    ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
    bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(0.0, a.w * a.h)
    area_b = max(0.0, b.w * b.h)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


@dataclass(slots=True)
class PersonCluster:
    """Один непрерывный шот человека.

    Содержит список детекций (`samples`) в временном порядке, границы
    `start_sec`/`end_sec` и сводную bbox-статистику.
    """

    id: int
    samples: list[FrameDetection] = field(default_factory=list)
    start_sec: float = 0.0
    end_sec: float = 0.0

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)

    @property
    def centroid_bbox(self) -> FaceBBox | None:
        """Средний bbox по всем samples (proxy для геометрии шота)."""
        faces = [s.primary_face for s in self.samples if s.primary_face]
        if not faces:
            return None
        n = len(faces)
        return FaceBBox(
            x=sum(f.x for f in faces) / n,
            y=sum(f.y for f in faces) / n,
            w=sum(f.w for f in faces) / n,
            h=sum(f.h for f in faces) / n,
            confidence=sum(f.confidence for f in faces) / n,
        )

    def iou_with(self, other: PersonCluster) -> float:
        """Геометрическая похожесть центроидов — proxy для same-composition.

        Fashion ranker использует это чтобы находить кандидатов на склейку
        из разных шотов с одинаковой композицией кадра.
        """
        c1 = self.centroid_bbox
        c2 = other.centroid_bbox
        if c1 is None or c2 is None:
            return 0.0
        return _iou(c1, c2)


def cluster_persons(result: FaceTrackResult) -> list[PersonCluster]:
    """Группирует `FrameDetection` в shot-level кластеры.

    Отфильтровывает кластеры короче ``MIN_DURATION_SEC`` — они обычно шум
    (ложные детекции на одном кадре).
    """
    clusters: list[PersonCluster] = []
    active: list[PersonCluster] = []
    next_id = 0

    for det in result.detections:
        face = det.primary_face
        if face is None:
            continue
        t = det.timestamp_sec

        # Закрываем кластеры, которые "протухли" (gap > MAX_GAP_SEC)
        still_active: list[PersonCluster] = []
        for cl in active:
            if t - cl.end_sec <= MAX_GAP_SEC:
                still_active.append(cl)
            else:
                clusters.append(cl)
        active = still_active

        # Ищем лучший кластер для расширения по IoU
        best_cl: PersonCluster | None = None
        best_iou = 0.0
        for cl in active:
            last_face = cl.samples[-1].primary_face
            if last_face is None:
                continue
            iou = _iou(last_face, face)
            if iou > best_iou and iou >= IOU_THRESHOLD:
                best_cl = cl
                best_iou = iou

        if best_cl is None:
            best_cl = PersonCluster(
                id=next_id, samples=[], start_sec=t, end_sec=t
            )
            next_id += 1
            active.append(best_cl)

        best_cl.samples.append(det)
        best_cl.end_sec = t

    clusters.extend(active)

    significant = [c for c in clusters if c.duration_sec >= MIN_DURATION_SEC]
    log.info(
        "person_cluster.done",
        extra={
            "total_samples": len(result.detections),
            "raw_clusters": len(clusters),
            "significant_clusters": len(significant),
            "dropped_short": len(clusters) - len(significant),
        },
    )
    return significant


__all__ = [
    "IOU_THRESHOLD",
    "MAX_GAP_SEC",
    "MIN_DURATION_SEC",
    "PersonCluster",
    "cluster_persons",
]
