"""Smoke-тест `JobService.update_vision_profile` — 2.3."""

from __future__ import annotations

from videomaker.models.job import JobCreate, VisionProfile
from videomaker.services.jobs import JobService


async def test_update_vision_profile_persists(clean_db) -> None:
    service = JobService()
    payload = JobCreate(
        transcriber="mlx_whisper",
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
    )
    job = await service.create(
        source_path="/tmp/fake.mp4",
        source_filename="fake.mp4",
        source_size_bytes=100,
        payload=payload,
    )
    assert job.vision_profile == VisionProfile.talking_head

    updated = await service.update_vision_profile(
        job.id, profile=VisionProfile.fashion
    )
    assert updated is not None
    assert updated.vision_profile == VisionProfile.fashion


async def test_update_vision_profile_missing_job_returns_none(clean_db) -> None:
    service = JobService()
    result = await service.update_vision_profile(
        "nonexistent-id", profile=VisionProfile.fashion
    )
    assert result is None


async def test_update_vision_profile_same_value_is_noop(clean_db) -> None:
    service = JobService()
    payload = JobCreate()
    job = await service.create(
        source_path="/tmp/f.mp4",
        source_filename="f.mp4",
        source_size_bytes=50,
        payload=payload,
    )
    # Second update to the same profile — should return the job unchanged.
    result = await service.update_vision_profile(
        job.id, profile=VisionProfile.talking_head
    )
    assert result is not None
    assert result.vision_profile == VisionProfile.talking_head
