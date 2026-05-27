"""Управление файловыми артефактами пайплайна."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from videomaker.core.config import get_settings


class ArtifactsManager:
    """Организует иерархию артефактов на диске: <artifacts_dir>/<job_id>/<kind>/...

    kinds:
      source/   — исходный медиафайл (или симлинк)
      audio/    — извлечённая аудиодорожка, нарезки для STT
      text/     — JSON: transcript, cleaned_transcript, reel_plan
      reels/    — финальные mp4 нарезки
      subs/     — ASS-файлы субтитров
      logs/     — pipeline-логи пошагово
    """

    ALLOWED_KINDS = frozenset(
        {
            "source",
            "audio",
            "text",
            "reels",
            "subs",
            "logs",
        }
    )

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = (root or settings.app_artifacts_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        if not job_id or "/" in job_id or ".." in job_id:
            raise ValueError(f"invalid job_id: {job_id!r}")
        path = (self.root / job_id).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("resolved path escapes artifacts root")
        return path

    def ensure_layout(self, job_id: str) -> Path:
        base = self.job_dir(job_id)
        for kind in self.ALLOWED_KINDS:
            (base / kind).mkdir(parents=True, exist_ok=True)
        return base

    def path_for(self, job_id: str, kind: str, name: str) -> Path:
        if kind not in self.ALLOWED_KINDS:
            raise ValueError(f"unknown artifact kind: {kind!r}")
        if not name or "/" in name or ".." in name:
            raise ValueError(f"invalid artifact name: {name!r}")
        return self.job_dir(job_id) / kind / name

    def resolve_relative(self, job_id: str, relative_path: str) -> Path:
        """Безопасно превращает artifact.path (relative) в абсолютный путь.

        Рейзит ValueError если путь выходит за пределы job_dir (traversal attack).
        """
        if not relative_path:
            raise ValueError("empty relative path")
        base = self.job_dir(job_id)
        candidate = (base / relative_path).resolve()
        if base not in candidate.parents and candidate != base:
            raise ValueError("resolved path escapes job dir")
        return candidate

    def saved_dir(self, job_id: str, subfolder: str | None = None) -> Path:
        """Путь к под-папке ``saved/`` внутри job_dir.

        Используется для ручных подборок отобранных рилсов
        (Копировать отобранные → `<job_dir>/saved/<subfolder>/`).
        """
        base = self.job_dir(job_id) / "saved"
        if subfolder is None:
            return base
        safe = subfolder.strip()
        if not safe or "/" in safe or ".." in safe:
            raise ValueError(f"invalid saved subfolder: {subfolder!r}")
        return base / safe

    def write_json(self, job_id: str, name: str, payload: dict[str, Any]) -> Path:
        path = self.path_for(job_id, "text", name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        return path

    def read_json(self, job_id: str, name: str) -> dict[str, Any]:
        path = self.path_for(job_id, "text", name)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"expected JSON object at {path}, got {type(data).__name__}")
        return data

    def delete_job(self, job_id: str) -> None:
        base = self.job_dir(job_id)
        if base.exists():
            shutil.rmtree(base)
