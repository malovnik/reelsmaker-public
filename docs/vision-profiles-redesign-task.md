# Vision Profiles + Transcription Cache + Frontend Redesign — Ralph Loop Task

Реализуй большой блок фич для videomaker. 6 последовательных фаз с commit+push между ними.

## PHASE 1 — Transcription Cache

- SHA256 content hash от видеофайла (реиспользуй паттерн VisionResultCache из apps/backend/src/videomaker/vision/cache.py)
- Storage: data/transcripts/{sha}.json с метаданными (backend, lang, duration, wpm)
- Invalidation: mtime + явный force_reingest flag в ProjectSettings
- Hook в transcriber_factory: check cache до вызова mlx-whisper/Deepgram
- UI: индикатор transcript cached в upload wizard + progress SSE cache_hit событие
- Тесты: минимальный pytest на cache hit/miss/force_reingest

## PHASE 2 — Vision Profile enum + auto-detect

- Enum VisionProfile: talking_head (default), fashion, travel, screencast, custom
- Store в ProjectSettings (SQLAlchemy) + runtime_settings_store дефолт
- Auto-detect heuristic post-transcript: WPM + silence ratio + vision-layer face coverage
  - меньше 40 WPM ИЛИ больше 70 процентов silence → предложить fashion/travel
  - больше 120 WPM + больше 60 процентов face coverage → talking_head
- UI upload wizard: явный выбор профиля + auto-detect suggestion chip
- API: PATCH /api/v1/projects/ID/profile

## PHASE 3 — Fashion Profile pipeline

- Skip text-heavy Gemini агентов когда wpm низкий (конфиг per-profile agent mask)
- Priority chain: visual evidence → face tracker → zoom planner → cover selector
- Same-person clustering: face embedding (уже есть в face_tracker) → cluster по косинусной близости
- Multi-location beautiful transitions: выбор клипов с одинаковой person_id но разными scene_id
- Composition anchor: target bbox из Moondream face_framing → интерполятор из zoom_planner
- Fallback: если vision disabled, fashion profile работает как talking_head (инвариант — не падаем)
- Story Doctor: per-profile re-rank веса (visual_weight для fashion, story_weight для talking_head)

## PHASE 4 — Talking Head composition enhancement

- talking_head + vision_enabled → hard-gate face centering через Moondream validator
- Story Doctor penalty коэффициент за off-center клипы (face bbox center deviation)
- Vision disabled → byte-identical standard pipeline (CRITICAL инвариант: no regressions)
- Variant кропов: auto 9:16 crop по face center из vision cache

## PHASE 5 — Frontend redesign (light futuristic)

- Behance research через WebFetch/WebSearch: editorial creative dashboard, futuristic AI tool UI
- Palette: light base (zinc-50/white) + cyan→violet accent gradient + glassmorphism cards
- Typography: Inter для UI + JetBrains Mono для metadata
- Framer Motion micro-interactions: hover elevate, progress shimmer, stage transitions
- Новые компоненты:
  - ProfileSelectorCard (пять профилей с превью иллюстрацией)
  - TranscriptCacheBadge (hit/miss/force)
  - VisionPreviewGallery (grid face-framed кадров из cache)
  - PipelineStageTimeline (вертикальная)
- Миграция всех views: dashboard, upload wizard, project overview, settings/models, settings/stt, settings/prompts
- Dark mode preserve как secondary theme (не удаляем, но light = primary)
- Mobile-first адаптив

## PHASE 6 — QA + production polish

- uv run pytest (backend)
- ruff check + ruff format (backend)
- pyright (backend)
- pnpm lint + npx tsc --noEmit + pnpm build (frontend)
- E2E smoke: fashion video full pipeline + cached transcript rerun
- 6+ коммитов, push после каждой фазы

## Chain of Thought + мультироли

- Senior Python Backend Architect — чистые интерфейсы, защита от регрессий, invariant preservation
- ML Engineer Vision — face embedding clustering, composition anchor math
- Frontend Architect — Next.js 16 App Router paradigms, React 19 use() patterns
- Product Designer — Behance research, light futuristic без минимализма, eye-pleasing interactive
- QA Engineer — smoke tests only (токены беречь)
- Release Engineer — atomic commits, push per phase, rollback strategy

## Правила

- 1 цикл = 1 микрозадача
- Production-grade: no mocks, no TODO, no FIXME, no placeholders
- Serena для кода, Context7 для документации (Next.js 16, Framer Motion, SQLAlchemy)
- НЕ swarm агентов — реализация последовательно, чтобы не сломать архитектуру
- Логирование прогресса: TaskUpdate + Serena write_memory после каждой фазы
- Документация решений: docs/ + Serena memories
- Мобайл + desktop адаптив с первой итерации

## Дефолты (из обсуждения с user)

- Palette: cyan→violet gradient, light base primary
- Fashion v1: one person / multiple locations (multi-person — отдельная фаза потом)
- Transcription cache: SHA256 content hash (robust, matches VisionResultCache pattern)
- Контекст: пользователь делает контент для жены-стилиста — нужны эффектные рилсы

## Первая итерация

План с микрозадачами запиши через Superpowers brainstorming в:
<source-repo>/docs/vision-profiles-redesign-plan.md

Читай план первым делом каждый цикл. Обновляй Status после каждой микрозадачи.

По завершении всех 6 фаз с коммитами + мемори + QA зелёный — вывести completion_promise VISION-PROFILES-REDESIGN-COMPLETE
