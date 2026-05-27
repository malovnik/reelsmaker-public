# Phase 5 — Валидация PRD: сводка

> 3 валидатора (полнота / реализуемость / консистентность). Все находки внесены в PRD-expose.md.

## Вердикт: PRD был НЕПОЛОН → исправлен → ГОТОВ к Phase 6.

## Внесённые исправления
| # | Находка (кем) | Правка в PRD |
|---|---------------|--------------|
| 1 | **BR-06 пропущен (P0)** — отмена публикации не покрыта (нашли 2 из 3 валидаторов независимо) | Добавлен R2.6: реальный Publer retract |
| 2 | EPIC 5 неверный путь (feasibility) — reels_composer это LLM-слой | Уточнён реальный путь render.py→ProjectRenderer→build_filter_graph |
| 3 | EPIC 5 портируемость — renderer.py:54 хардкод hevc_videotoolbox | R5.2: общий runtime-детект энкодера + libx264 |
| 4 | R4.2 премиса устарела — liked уже str-enum обе стороны, 422-риска нет | R4.2 → verify-only |
| 5 | EPIC 7 — to_thread непрерываем, naive timeout не убьёт hang | R7.1 → process-изоляция с kill |
| 6 | R2.1 — POST /jobs не принимает project_id | Связка через PATCH /jobs/{id}/project |
| 7 | EPIC 9 — object_tracker НЕ orphan (живой импорт zoom_planner) | Только 4 подтверждённых + B-roll с проверкой BRollSpec |
| 8 | H2 — cursor-zoom default не выключен | R9.2: флип в False |
| 9 | Слабые критерии приёмки (9 шт) | Переписаны на измеримые (ffprobe, имя модели в логе, grep+E2E) |

## Остаётся как есть (обоснованно)
- Auth WONTFIX, persistent queue вне скоупа — подтверждено, отражено в ROADMAP.
- Порядок реализации корректен (EPIC1→3→4→2→6→5→7→8→9).
