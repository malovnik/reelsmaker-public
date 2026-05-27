# README Truth Validation — Фичи / Тех-стек (Reelibra)

Проверено против кода: `apps/frontend/src`, `apps/backend/src`, `run.sh`, `package.json`, `pyproject.toml`. Дата: 2026-05-27.

## 1. Два режима интерфейса — ПРАВДА

- **Пошаговый (мастер):** `contexts/UiModeContext.tsx` (`UiMode = "guided" | "expert"`, default `guided`). Гайдед-флоу — `components/upload/guided/GuidedFlow.tsx`, рендерится в `HomeClient.tsx:192` при `isGuided`. ПРАВДА.
- **Эксперт-студия + tooltip на каждом контроле:** `UploadWizard.tsx` (рендерится при expert), подсказки — `components/settings-shared/controlHints.ts` (реестр what/effect/advise/badge на каждый контрол) + `hintAdornment.tsx` (используется в 9 местах). В контроле комментарий: «покрытие подсказками — инвариант, а не дисциплина» (типобезопасно через `hintKey`). ПРАВДА.

## 2. Список фич — все ПРАВДА

| Фича | Статус | Где в коде |
|------|--------|-----------|
| Авто-нарезка длинного видео на набор рилсов | ПРАВДА | `services/pipeline.py`, `services/narrative/`, `pipeline_stages/` |
| Транскрипция речи | ПРАВДА | `services/transcribers/` (factory + 3 бэкенда) |
| Субтитры с настраиваемым стилем | ПРАВДА | `SubtitleStyleEditor.tsx`, `SubtitleSettingsClient.tsx`, `services/subtitle_store` |
| Выравнивание громкости | ПРАВДА | `services/audio_normalizer.py`, dep `pyloudnorm` |
| Swipe-отбор (tinder) | ПРАВДА | `pages/JobTinderPage.tsx` → `components/job/TinderClient.tsx` |
| Правка субтитров | ПРАВДА | `jobs.py:1335` (raw .ass GET) + `jobs.py:1353 update_reel_subtitles` (T3.4 captions editor) |
| Экспорт под платформы | ПРАВДА | `jobs.py:1461 export_reel_with_preset`, `config/export_presets.yaml` (reels_9_16, shorts_16_9), real-transcode под preset bitrate |
| Publer-публикация | ПРАВДА | `services/publer/` (client, worker, media_uploader, caption_generator) + frontend scheduler/* |
| Проекты-папки | ПРАВДА | `api/routes/projects.py`, frontend `components/projects/` (ProjectFolder, ProjectsList) |
| Vision off-default | ПРАВДА | `models/vision_settings.py:35 enabled: bool = False` |

## 3. Виртуальный монтаж (LLM собирает рилсы из разных частей) — ПРАВДА (с нюансом)

- Narrative-пайплайн существует: `services/narrative/` (orchestrator, map_reduce_orchestrator, arc_finder, chapter_builder, cross_chapter_ranker, hook_detector). LLM анализирует транскрипт по драматургии.
- **Multi-segment сборка из разных частей** реальна в Viral 2026 режиме: `viral_arc_builder.py` — `segments: list[_LLMSegment]`, один рилс из нескольких `segments[].start/.end`.
- **Нюанс (не ошибка):** top-down arc_finder (`narrative_arc_finder.md`) внутри одной главы берёт НЕПРЕРЫВНЫЙ слайс hook→payoff (не склейка фрагментов). То есть «из разных частей исходника» — точно про межглавный/viral уровень и выбор не-подряд кусков таймлайна, а не про склейку внутри одного рилса во всех режимах. Утверждение README в целом корректно (несколько narrative-режимов, контролируются `narrative_mode`), не вводит в заблуждение.

## 4. Тех-стек — ПРАВДА

- FastAPI порт 8000: ПРАВДА — `pyproject.toml fastapi>=0.115`, `run.sh` `--port ${APP_PORT:-8000}`, `config.py` default 8000.
- React 19 + Vite порт 3000: ПРАВДА — `package.json react ^19.2.5`, `vite ^7`, `vite.config.ts: port: 3000`.
- SQLite: ПРАВДА — `aiosqlite`, `sqlalchemy`, `app_db_path = data/videomaker.db`.
- `./run.sh` для dev: ПРАВДА, файл существует и поднимает оба сервиса.

### ЗАБЫТО / НЕТОЧНОСТЬ (минорно):
- README п.77/153: «нужны установленные `uv`, `node`, `ffmpeg`». **Фактически `run.sh` требует `uv`, `pnpm`, `ffmpeg`** — проверяет `command -v pnpm` (НЕ `node`), и frontend ставится через `pnpm install` / `pnpm dev`. Указан `node` вместо `pnpm`. Технически node нужен для pnpm, но прямая проверка в run.sh — на `pnpm`, не на `node`. Рекомендация: заменить `node` → `pnpm` (или дописать pnpm) в обоих языковых блоках README.

## 5. STT: Apple Silicon → MLX stable_ts_mlx, иначе Deepgram — ПРАВДА

- `core/config.py:16 DEFAULT_TRANSCRIBER = "stable_ts_mlx" if IS_MACOS else "deepgram"`.
- `transcribers/factory.py`: MLX-бэкенды гейтятся `sys.platform != "darwin"` → ошибка с подсказкой про Deepgram. Deepgram требует `DEEPGRAM_API_KEY`.
- `pyproject.toml`: `stable-ts[mlx]` и `mlx-whisper` гейтятся `sys_platform == 'darwin'`. ПРАВДА.
- Нюанс: README относит Intel-Mac к Deepgram. Код различает только `darwin` vs не-darwin (Intel-Mac = darwin → попытается MLX). На Intel-Mac MLX физически не запустится (нет Apple Silicon), так что фактически Intel-Mac упрётся в Deepgram — README честнее кода тут, противоречия для пользователя нет.

## 6. «Локальные данные не покидают компьютер» (кроме облачного LLM/Deepgram) — ПРАВДА

- `config.py`: `data/videomaker.db`, `data/artifacts`, `data/uploads`, `data/models`, `face_cache` — всё в `REPO_ROOT/data/`. Локально.
- Облако: Gemini (`google-genai`), опц. Zhipu (`zhipuai`), Deepgram (`deepgram-sdk`) на не-Mac, Publer (опц., при публикации). README перечисляет облачные исключения корректно (LLM + Deepgram). Honest.

## 7. Приписанные / забытые фичи

**Приписанных (несуществующих) фич НЕ найдено** — все 10 фич + 2 режима + тех-стек подтверждены кодом.

**Минорные неточности:**
1. `run.sh` требует `pnpm`, а README пишет `node` (п.4 выше). Единственная фактическая нестыковка.
2. README не упоминает существующие в коде доп. фичи (scheduler/campaigns, brand kit, presets, vision-профили, performance/post-production настройки, models page) — это НЕ ошибка (README не обязан перечислять всё), приписывания нет.

## Вердикт
README по фичам и тех-стеку **достоверен**. Несуществующих фич не приписано, ограничения (Vision/face-tracking off, CPU-кодирование медленное, Deepgram-зависимость на Win/Linux) указаны честно. Единственная правка по существу: `node` → `pnpm` в разделе ручного запуска.
