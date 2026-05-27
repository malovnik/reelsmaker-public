"""Ad-hoc CLI: рендерит один ProjectGraph из JSON-файла.

Usage:
    uv run python scripts/render_one_graph.py /path/to/project_graph.json [output.mp4]

Если `output.mp4` не указан — берётся `output_path` из самого графа.
Полезно для отладки v0.5 builder/renderer без полного pipeline.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from videomaker.services.project_graph import ProjectGraph
from videomaker.services.project_renderer import (
    DEFAULT_RENDER_CONCURRENCY,
    ProjectRenderer,
    RenderProgress,
)


async def _amain(graph_path: Path, output_override: Path | None) -> int:
    payload = graph_path.read_text(encoding="utf-8")
    graph = ProjectGraph.model_validate_json(payload)
    if output_override is not None:
        graph = graph.model_copy(update={"output_path": str(output_override)})

    renderer = ProjectRenderer()

    last_pct = -1.0

    async def on_progress(snap: RenderProgress) -> None:
        nonlocal last_pct
        total = sum(c.duration_sec for c in graph.cuts)
        pct = (snap.out_time_sec / total * 100.0) if total > 0 else 0.0
        if pct - last_pct >= 5.0 or snap.finished:
            last_pct = pct
            print(
                f"[{graph.reel_id}] {pct:6.1f}% frame={snap.frame:>6}"
                f" fps={snap.fps:5.1f} speed={snap.speed or '-'}"
            )

    result = await renderer.render(graph, on_progress=on_progress)
    print()
    print(f"reel_id        : {result.reel_id}")
    print(f"output_path    : {result.output_path}")
    print(f"duration_sec   : {result.duration_sec:.2f}")
    print(f"file_size_mb   : {result.file_size_bytes / (1024 * 1024):.2f}")
    print(f"bitrate_kbps   : {result.bitrate_bps // 1000 if result.bitrate_bps else '-'}")
    print(f"wall_time_sec  : {result.wall_time_sec:.2f}")
    print(f"concurrency    : {DEFAULT_RENDER_CONCURRENCY} (default)")
    if result.loudnorm:
        ln = result.loudnorm
        print(
            f"loudnorm       : target={ln.target_lufs} achieved={ln.output_integrated_lufs:.2f}"
            f" within_tol={ln.is_within_tolerance}"
        )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_one_graph.py <project_graph.json> [output.mp4]", file=sys.stderr)
        return 2
    graph_path = Path(sys.argv[1])
    if not graph_path.exists():
        print(f"file not found: {graph_path}", file=sys.stderr)
        return 1
    output_override = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
    return asyncio.run(_amain(graph_path, output_override))


if __name__ == "__main__":
    sys.exit(main())
