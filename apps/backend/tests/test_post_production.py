"""Unit-тесты post-production: asset_store + post_production_store.

Покрывает:
* Импорт asset с реальным ffprobe (synth_video fixture).
* SHA256-дедупликация: повторный импорт того же файла не дублирует row.
* Валидация (пустой файл, невалидное видео).
* Удаление asset с проверкой in-use (ON DELETE RESTRICT + сервисный guard).
* CRUD пресетов: create, list, get, update, delete.
* Инвариант "ровно один is_default" — установка нового default сбрасывает старый.
* Asset reference validation (несуществующий intro_asset_id → 400).
* Защита от удаления пресета с активными jobs (running/pending).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from videomaker.models.job import Job, JobStatus
from videomaker.models.post_production import (
    PostProductionConfig,
    PostProductionPresetCreate,
    PostProductionPresetUpdate,
    VideoAssetRow,
)
from videomaker.services import asset_store, post_production_store

# ─────────────────────── asset_store tests ────────────────────────


async def test_import_asset_creates_row_with_metadata(
    clean_db, synth_video, tmp_path: Path
) -> None:
    src = synth_video(duration=2.0, name="intro_test")
    # Скопируем во "входящий" temp-каталог (имитация того, что роут уже принял upload)
    temp_path = tmp_path / "_pending.tmp"
    temp_path.write_bytes(src.read_bytes())

    row, created = await asset_store.import_asset(
        temp_path=temp_path,
        name="My Intro",
        original_filename="intro.mp4",
    )

    assert created is True
    assert row.id is not None
    assert row.name == "My Intro"
    assert row.duration_sec == pytest.approx(2.0, abs=0.2)
    assert row.width == 320
    assert row.height == 240
    assert row.video_codec == "h264"
    assert row.audio_codec == "aac"
    assert Path(row.file_path).exists(), "файл должен быть перенесён в assets_dir"
    assert not temp_path.exists(), "temp удаляется после переноса"


async def test_import_asset_dedup_by_sha256(
    clean_db, synth_video, tmp_path: Path
) -> None:
    src = synth_video(duration=1.5, name="outro_test")
    # Первый импорт
    temp1 = tmp_path / "first.tmp"
    temp1.write_bytes(src.read_bytes())
    row1, created1 = await asset_store.import_asset(
        temp_path=temp1, name="Outro v1", original_filename="outro.mp4"
    )
    assert created1 is True

    # Повторный импорт тех же байт под другим именем → должен вернуть существующий row
    temp2 = tmp_path / "second.tmp"
    temp2.write_bytes(src.read_bytes())
    row2, created2 = await asset_store.import_asset(
        temp_path=temp2,
        name="Совершенно другой outro",
        original_filename="different_name.mp4",
    )

    assert created2 is False
    assert row2.id == row1.id
    assert row2.name == "Outro v1", "имя из существующей записи, не нового импорта"
    assert row2.file_hash == row1.file_hash
    assert not temp2.exists()


async def test_import_asset_rejects_empty_file(clean_db, tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")

    with pytest.raises(asset_store.AssetValidationError, match="empty"):
        await asset_store.import_asset(
            temp_path=empty, name="Bad", original_filename="empty.mp4"
        )


async def test_import_asset_rejects_invalid_video(
    clean_db, tmp_path: Path
) -> None:
    not_a_video = tmp_path / "garbage.mp4"
    not_a_video.write_bytes(b"this is not a valid video file" * 50)

    with pytest.raises(asset_store.AssetValidationError):
        await asset_store.import_asset(
            temp_path=not_a_video,
            name="Garbage",
            original_filename="garbage.mp4",
        )


async def test_delete_asset_removes_file_and_row(
    clean_db, synth_video, tmp_path: Path
) -> None:
    src = synth_video(duration=1.0, name="delete_me")
    temp = tmp_path / "tmp.mp4"
    temp.write_bytes(src.read_bytes())
    row, _ = await asset_store.import_asset(
        temp_path=temp, name="ToDelete", original_filename="x.mp4"
    )
    file_path = Path(row.file_path)
    assert file_path.exists()

    await asset_store.delete_asset(row.id)

    assert not file_path.exists()
    with pytest.raises(asset_store.AssetNotFoundError):
        await asset_store.get_asset(row.id)


async def test_delete_asset_blocked_when_referenced_by_preset(
    clean_db, synth_video, tmp_path: Path
) -> None:
    src = synth_video(duration=1.0, name="referenced")
    temp = tmp_path / "ref.tmp"
    temp.write_bytes(src.read_bytes())
    asset, _ = await asset_store.import_asset(
        temp_path=temp, name="Referenced", original_filename="r.mp4"
    )

    preset = await post_production_store.create_preset(
        PostProductionPresetCreate(
            name="P1", intro_asset_id=asset.id, config=PostProductionConfig()
        )
    )

    with pytest.raises(asset_store.AssetInUseError) as exc_info:
        await asset_store.delete_asset(asset.id)
    assert preset.id in exc_info.value.preset_ids

    # Файл должен остаться нетронутым после неудачного удаления
    assert Path(asset.file_path).exists()


# ─────────────────── post_production_store tests ──────────────────


async def _make_dummy_asset(name: str = "dummy.mp4") -> VideoAssetRow:
    """Создаёт фейковый VideoAssetRow напрямую в БД (без реального файла на диске).

    Используется в тестах CRUD пресетов, где сам файл не нужен — только id для FK.
    """

    from videomaker.core.db import session_scope

    fake_hash = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
    row = VideoAssetRow(
        name=name,
        file_path=f"/tmp/fake_asset_{fake_hash[:8]}.mp4",
        file_hash=fake_hash,
        file_size_bytes=1024,
        duration_sec=10.0,
        width=1080,
        height=1920,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        sample_rate=48000,
        channels=2,
    )
    async with session_scope() as session:
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return row


async def test_create_preset_with_defaults(clean_db) -> None:
    payload = PostProductionPresetCreate(name="Базовый")
    row = await post_production_store.create_preset(payload)

    assert row.id is not None
    assert row.name == "Базовый"
    assert row.is_default is False
    assert row.intro_asset_id is None
    assert row.outro_asset_id is None
    assert row.audio_normalize_enabled is True
    assert row.audio_target_lufs == -14.0
    assert row.zoom_enabled is False
    assert row.zoom_close_percent == 30


async def test_default_invariant_only_one(clean_db) -> None:
    """Создание второго default-пресета должно сбросить флаг у первого."""

    p1 = await post_production_store.create_preset(
        PostProductionPresetCreate(name="A", is_default=True)
    )
    p2 = await post_production_store.create_preset(
        PostProductionPresetCreate(name="B", is_default=True)
    )

    p1_after = await post_production_store.get_preset(p1.id)
    p2_after = await post_production_store.get_preset(p2.id)

    assert p1_after.is_default is False, "старый default сброшен"
    assert p2_after.is_default is True

    default = await post_production_store.get_default_preset()
    assert default is not None
    assert default.id == p2.id


async def test_create_preset_invalid_asset_ref(clean_db) -> None:
    with pytest.raises(post_production_store.AssetReferenceError) as exc:
        await post_production_store.create_preset(
            PostProductionPresetCreate(
                name="WithBadIntro", intro_asset_id=999999
            )
        )
    assert "999999" in str(exc.value)


async def test_create_preset_with_real_asset_ref(clean_db) -> None:
    asset = await _make_dummy_asset("test.mp4")
    payload = PostProductionPresetCreate(
        name="WithAsset",
        intro_asset_id=asset.id,
        outro_asset_id=asset.id,  # тот же asset как intro и outro — допустимо
    )
    row = await post_production_store.create_preset(payload)

    assert row.intro_asset_id == asset.id
    assert row.outro_asset_id == asset.id


async def test_update_preset_changes_default(clean_db) -> None:
    p1 = await post_production_store.create_preset(
        PostProductionPresetCreate(name="A", is_default=True)
    )
    p2 = await post_production_store.create_preset(
        PostProductionPresetCreate(name="B", is_default=False)
    )

    # Перевести default на p2
    updated = await post_production_store.update_preset(
        p2.id, PostProductionPresetUpdate(is_default=True)
    )
    p1_after = await post_production_store.get_preset(p1.id)

    assert updated.is_default is True
    assert p1_after.is_default is False


async def test_update_preset_changes_zoom_settings(clean_db) -> None:
    p = await post_production_store.create_preset(
        PostProductionPresetCreate(name="Zoom test")
    )
    new_config = PostProductionConfig(
        zoom_enabled=True,
        zoom_close_percent=40,
        zoom_subsegment_min_sec=3.0,
        zoom_subsegment_max_sec=8.0,
    )
    updated = await post_production_store.update_preset(
        p.id, PostProductionPresetUpdate(config=new_config)
    )

    assert updated.zoom_enabled is True
    assert updated.zoom_close_percent == 40
    assert updated.zoom_subsegment_min_sec == 3.0
    assert updated.zoom_subsegment_max_sec == 8.0


async def test_delete_preset_blocked_by_active_jobs(clean_db) -> None:
    """Если есть pending/running job со ссылкой на preset — удалять нельзя."""

    from videomaker.core.db import session_scope

    preset = await post_production_store.create_preset(
        PostProductionPresetCreate(name="ToBlock")
    )

    job_id = str(uuid.uuid4())
    async with session_scope() as session:
        job = Job(
            id=job_id,
            source_path="/tmp/fake.mp4",
            source_filename="fake.mp4",
            source_size_bytes=1000,
            status=JobStatus.running,
            progress=50,
            transcriber="mlx_whisper",
            llm_provider="gemini",
            llm_model="gemini-2.5-flash",
            target_aspect="9:16",
            fit_mode="fill",
            source_language="auto",
            post_production_preset_id=preset.id,
            options={},
        )
        session.add(job)

    with pytest.raises(post_production_store.PresetInUseError) as exc:
        await post_production_store.delete_preset(preset.id)
    assert job_id in exc.value.job_ids


async def test_delete_preset_ok_when_only_done_jobs(clean_db) -> None:
    """Завершённые jobs (done/error) не блокируют удаление —
    их FK SET NULL и история сохранится через post_production_config_json snapshot."""

    from videomaker.core.db import session_scope

    preset = await post_production_store.create_preset(
        PostProductionPresetCreate(name="OldPreset")
    )

    async with session_scope() as session:
        job = Job(
            id=str(uuid.uuid4()),
            source_path="/tmp/fake.mp4",
            source_filename="fake.mp4",
            source_size_bytes=1000,
            status=JobStatus.done,
            progress=100,
            transcriber="mlx_whisper",
            llm_provider="gemini",
            llm_model="gemini-2.5-flash",
            target_aspect="9:16",
            fit_mode="fill",
            source_language="auto",
            post_production_preset_id=preset.id,
            options={},
        )
        session.add(job)

    await post_production_store.delete_preset(preset.id)

    with pytest.raises(post_production_store.PresetNotFoundError):
        await post_production_store.get_preset(preset.id)


async def test_build_snapshot_includes_asset_paths(clean_db) -> None:
    asset = await _make_dummy_asset("intro.mp4")
    preset = await post_production_store.create_preset(
        PostProductionPresetCreate(
            name="Snapshot test",
            intro_asset_id=asset.id,
            config=PostProductionConfig(zoom_enabled=True, zoom_close_percent=25),
        )
    )

    row, intro, outro, companion = await post_production_store.get_preset_with_assets(preset.id)
    snapshot = post_production_store.build_snapshot(row, intro, outro, companion)

    assert snapshot.intro_path == asset.file_path
    assert snapshot.outro_path is None
    assert snapshot.zoom_enabled is True
    assert snapshot.zoom_close_percent == 25


async def test_list_presets_orders_default_first(clean_db) -> None:
    await post_production_store.create_preset(
        PostProductionPresetCreate(name="ZZZ Last alpha")
    )
    await post_production_store.create_preset(
        PostProductionPresetCreate(name="AAA Should be 2nd", is_default=False)
    )
    await post_production_store.create_preset(
        PostProductionPresetCreate(name="MID Default", is_default=True)
    )

    triples = await post_production_store.list_presets()
    names = [t[0].name for t in triples]

    assert names[0] == "MID Default", "default-пресет первым"
    # Остальные сортированы alphabetically
    assert names[1:] == ["AAA Should be 2nd", "ZZZ Last alpha"]
