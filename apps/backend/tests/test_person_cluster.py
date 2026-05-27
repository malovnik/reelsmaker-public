"""Smoke-тесты person_cluster (PHASE 3.2)."""

from __future__ import annotations

from videomaker.services.face_tracker import FaceBBox, FaceTrackResult, FrameDetection
from videomaker.services.person_cluster import (
    MAX_GAP_SEC,
    MIN_DURATION_SEC,
    cluster_persons,
)


def _bbox(x: float = 0.3, y: float = 0.3, w: float = 0.2, h: float = 0.3) -> FaceBBox:
    return FaceBBox(x=x, y=y, w=w, h=h, confidence=0.9)


def _det(ts: float, bbox: FaceBBox | None = None) -> FrameDetection:
    return FrameDetection(timestamp_sec=ts, faces=[bbox] if bbox else [])


def _make_result(detections: list[FrameDetection]) -> FaceTrackResult:
    return FaceTrackResult(
        video_path="/tmp/f.mp4",
        video_hash="abc",
        sample_interval_sec=0.5,
        frame_width=1920,
        frame_height=1080,
        detections=detections,
    )


def test_empty_detections_returns_empty_list() -> None:
    clusters = cluster_persons(_make_result([]))
    assert clusters == []


def test_single_continuous_shot_is_one_cluster() -> None:
    bbox = _bbox()
    detections = [_det(t, bbox) for t in [0.0, 0.5, 1.0, 1.5, 2.0]]
    clusters = cluster_persons(_make_result(detections))
    assert len(clusters) == 1
    assert clusters[0].duration_sec == 2.0
    assert len(clusters[0].samples) == 5


def test_gap_larger_than_max_creates_new_cluster() -> None:
    bbox = _bbox()
    first = [_det(t, bbox) for t in [0.0, 0.5, 1.0, 1.5]]
    second = [
        _det(t, bbox)
        for t in [1.5 + MAX_GAP_SEC + 1.0, 1.5 + MAX_GAP_SEC + 2.0]
    ]
    clusters = cluster_persons(_make_result(first + second))
    assert len(clusters) == 2


def test_bbox_jump_creates_new_cluster() -> None:
    bbox_left = _bbox(x=0.1, y=0.3, w=0.15, h=0.2)
    bbox_right = _bbox(x=0.75, y=0.3, w=0.15, h=0.2)
    detections = [
        _det(0.0, bbox_left),
        _det(0.5, bbox_left),
        _det(1.0, bbox_right),  # далеко от bbox_left → новый кластер
        _det(1.5, bbox_right),
        _det(2.0, bbox_right),
    ]
    clusters = cluster_persons(_make_result(detections))
    assert len(clusters) == 2
    centroids = [c.centroid_bbox for c in clusters]
    assert centroids[0] is not None and centroids[1] is not None


def test_short_cluster_below_threshold_is_dropped() -> None:
    bbox = _bbox()
    # Одна детекция — duration 0 → ниже MIN_DURATION_SEC
    clusters = cluster_persons(_make_result([_det(5.0, bbox)]))
    assert clusters == []


def test_missing_primary_face_skipped() -> None:
    bbox = _bbox()
    detections = [
        _det(0.0, bbox),
        _det(0.5, bbox),
        _det(1.0, None),  # пропускаем
        _det(1.5, bbox),
        _det(2.0, bbox),
    ]
    clusters = cluster_persons(_make_result(detections))
    assert len(clusters) == 1
    # Детекция без лица не попадает в samples
    assert all(s.primary_face is not None for s in clusters[0].samples)


def test_centroid_bbox_averages_samples() -> None:
    # bbox-ы близко друг к другу чтобы все попали в один кластер
    detections = [
        _det(0.0, _bbox(x=0.28, y=0.3, w=0.2, h=0.3)),
        _det(0.5, _bbox(x=0.32, y=0.3, w=0.2, h=0.3)),
        _det(1.0, _bbox(x=0.30, y=0.3, w=0.2, h=0.3)),
    ]
    clusters = cluster_persons(_make_result(detections))
    assert len(clusters) == 1
    centroid = clusters[0].centroid_bbox
    assert centroid is not None
    assert 0.29 < centroid.x < 0.31  # среднее (0.28+0.32+0.30)/3 = 0.30


def test_iou_with_measures_composition_similarity() -> None:
    bbox_a = _bbox(x=0.3, y=0.3, w=0.2, h=0.3)
    bbox_b = _bbox(x=0.32, y=0.32, w=0.2, h=0.3)  # почти совпадает
    det_a = [_det(t, bbox_a) for t in [0.0, 0.5, 1.0]]
    det_b = [_det(t, bbox_b) for t in [10.0, 10.5, 11.0]]  # разное время
    clusters = cluster_persons(_make_result(det_a + det_b))
    assert len(clusters) == 2
    similarity = clusters[0].iou_with(clusters[1])
    assert similarity > 0.5  # похожая композиция


def test_min_duration_filter_threshold() -> None:
    bbox = _bbox()
    # Длительность ровно MIN_DURATION_SEC — должна пройти
    passing = [_det(0.0, bbox), _det(MIN_DURATION_SEC, bbox)]
    clusters = cluster_persons(_make_result(passing))
    assert len(clusters) == 1


def test_person_cluster_id_increments() -> None:
    bbox = _bbox()
    far_bbox = _bbox(x=0.8, y=0.3)
    detections = [
        _det(0.0, bbox),
        _det(0.5, bbox),
        _det(1.0, far_bbox),
        _det(1.5, far_bbox),
    ]
    clusters = cluster_persons(_make_result(detections))
    assert len(clusters) == 2
    assert clusters[0].id != clusters[1].id
