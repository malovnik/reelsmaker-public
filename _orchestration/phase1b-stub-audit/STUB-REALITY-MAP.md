# STUB-REALITY-MAP — что реально работает vs «для вида»

> Консолидация 5 отчётов Phase 1b. Источник истины по статусу каждой фичи бэкенда.
> Легенда: 🟢 REAL · 🟡 PARTIAL/DORMANT · 🔴 FAKE/ORPHAN/BUG · 🔒 SECURITY

## 1. Живое ядро (работает по-настоящему на дефолте)
- Upload → job → ingest (probe → proxy-кэш → STT stable-ts MLX → translate если не RU → silence_cut). 🟢
- Narrative `bottom_up`: chunking → compression → canvas → 6 extraction-агентов → reduce → story_doctor (3-act) → rhythm → variants → compose → coherence + closure валидаторы. Десятки реальных Gemini Flash-Lite вызовов. 🟢 **Это сердце сервиса.**
- Render: ffmpeg HEVC граф — center-crop 9:16, cut_snap к словам, burn ASS-субтитров, two-pass loudnorm −14 LUFS. 🟢
- Аудио-DSP (VAD, loudnorm, adaptive leveller, beat-snap, breath/mouth-эвристики, filler removal, pause compression, 15-фичный анализатор) — всё вызывается из render.py. 🟢
- Publer: реальный httpx-клиент к Publer Business API v1 + background PublerWorker в lifespan. Доставляет queued-assignments. 🟢 (но отдельный ручной флоу, не часть pipeline)
- SSE live-прогресс. 🟢
- Персистентность: SQLite async, 12 таблиц, 11 store'ов реально пишут, 0 fake-store'ов. 🟢

## 2. Декоративное / выключенное на дефолте
| Фича | Статус | Доказательство | Действие |
|------|--------|----------------|----------|
| screencast cursor zoom | 🟡 DORMANT (toggle ВКЛ по умолч., жжёт CPU, выход выброшен) | render.py:1116,1133 | оживить (M) или выключить дефолт |
| deictic zoom | 🟡 DORMANT | render.py:1164 | оживить (S-M, free-ride на cursor zoom) |
| mouth-sound removal | 🟡 DORMANT | render.py:777 | оживить opt-in (M) |
| Vision-слой целиком | выключен kill-switch `vision_enabled=False` | runtime_settings | решение PRD |
| face tracking | 🟡 DISABLED-by-default (mediapipe hang на M-series) | runtime_settings.py:405 | решение PRD (flagship-фича тёмная) |
| B-roll subsystem | 🔴 ORPHAN (294 LOC, 0 вызовов) | broll/* | удалить или продукт-скоуп |
| object_tracker | 🔴 ORPHAN (live-caller всегда None) | render.py:566 | удалить (зависит от fake Moondream) |
| person_cluster, match_cuts, eye_trace_continuity, transition_chooser | 🔴 ORPHAN (~678 LOC, 0 ссылок) | — | удалить (~972 LOC мёртвого кода всего) |

## 3. Фикции, врущие пользователю в UI
| Фикция | Реальность | Доказательство | Действие |
|--------|-----------|----------------|----------|
| tier «pro»/«flash»/«flash_lite» | ВСЕ резолвятся в Flash-Lite; «Pro analytics» — фикция | tier_resolver.py:37-52 | честные лейблы / убрать обман |
| viral_2026 «уважает выбор провайдера» | молча жжёт Gemini при выбранном Zhipu, пишет `provider:gemini` при `user_requested_llm:zhipu` | viral_arc_builder.py:428, analysis.py:867-898 | 🐞 FIX (S, нужен GLM concurrency=1 gate) |
| narrative_mode `chaptered` | автор пометил broken, но выбираем из UI | map_reduce_orchestrator.py:18, analysis.py:242 | убрать из UI / починить |
| Claude/OpenAI провайдеры | мёртвый код в narrative (Gemini-only by MEMORY) | — | оставить (translator/auto_config) или скрыть из UI |
| per-stage fallback | тихо маскируют LLM-сбой → «успешный» job на эвристике | — | добавить degradation-флаг |
| Moondream `detect` | VQA-эвристика с фабрикованным bbox, не детекция | moondream_local.py:259-298 | переименовать `locate_heuristic`, не звать как детекцию |

## 4. Частичные заглушки ручек (LIES-200-noop)
| Ручка | Реальность | Доказательство | Действие |
|-------|-----------|----------------|----------|
| POST `/jobs/{id}/reels/{rid}/export` | нет транскода, `download_url`=исходный mp4, bitrate/lufs декларативны | jobs.py:1317-1347 | реальный ffmpeg transcode (M) |
| POST `/scheduler/assignments/{id}/cancel` | только local flip, нет DELETE в Publer (для доставленных) | scheduler.py:720-737 | дореализовать Publer-отзыв (M) |
| GET `/post_production/presets/default` | 200+null вместо 204 | post_production.py:210-216 | привести контракт (S) |

## 5. Корректность рантайма / безопасность
| Проблема | Вердикт | Доказательство | Приоритет | Действие |
|----------|---------|----------------|-----------|----------|
| `reel_id` path-traversal (PATCH subtitles = write-primitive!) | 🔒🔴 VULN | jobs.py:1263/1292/1298/1335 | P0 | regex `^[A-Za-z0-9_-]+$` + containment (S) |
| cancel job не работает (mark_cancelled нет, `_pipeline_tasks` не итерируется) | 🔴 DEAD-enum | jobs.py:1057,1365 | P1 | реализовать cancel (M) |
| `h264_videotoolbox` macOS-only в re-encode | 🔴 PORTABILITY (>180MB рилс на Linux) | media_uploader.py:104 | P1* | guard + libx264 fallback (S) |
| SQLite database-locked при параллельных флашах | 🟡 RACE | core/db.py (нет WAL/busy_timeout) | P2 | PRAGMA WAL + busy_timeout=30000 (S) |
| Полное отсутствие auth/authz/rate-limit | 🔒 MISSING | main.py:107-134 (только CORS) | DECISION | см. ниже |
| JobEventBus/кэши process-bound | 🟡 SCALING-stub | — | P3 | приемлемо для single-instance |
| fire-and-forget pipeline (рестарт=потеря джоб) | 🟡 | — | P2 | решение PRD (persistent queue) |

## Решение по auth (флаг для пользователя)
Сервис спроектирован как **локальный single-user инструмент** (Nikita, рилсы из Азии). Добавление auth — архитектурная развилка, НЕ подразумеваемая «доводкой до рабочего». Публичность РЕПО ≠ публичный деплой. **Решение: auth НЕ добавляем по умолчанию** (Karpathy-дисциплина: не добавлять незапрошенное); документируем как deploy-time concern. Path-traversal VULN чиним независимо (это баг при любом сценарии).

## План доводки 1b-fix (безопасные high-value фиксы — делаем сейчас)
1. 🔒 P0: path-traversal `reel_id` (regex+containment) — все 4 call-site.
2. 🐞 P1: viral_2026 provider_override — уважать выбор Zhipu + GLM concurrency gate.
3. 🐞 P1: videotoolbox guard + libx264 fallback (портируемость).
4. 🐞 P1: реализовать cancel job (mark_cancelled + отмена asyncio-task).
5. ⚙️ P2: SQLite WAL + busy_timeout PRAGMA.
6. 🧹 удалить ~972 LOC orphan (B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser) — после подтверждения нулевых ссылок.
7. 🏷️ честность: убрать tier-фикцию из лейблов / degradation-флаг для fallback / Moondream rename.
8. 🟡 dormant cursor zoom: выключить дефолт (не жечь CPU впустую) ИЛИ оживить — решит PRD; пока выключаем дефолт.

ОТЛОЖЕНО в PRD (Phase 4, продукт-решения): revival vision-слоя, face-tracking fix, B-roll как продукт, real export transcode, persistent job queue, chaptered fix.
