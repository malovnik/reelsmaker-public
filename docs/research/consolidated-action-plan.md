# Reelibra — Consolidated Action Plan

**Дата:** 2026-04-19
**Режим:** «Идеальный продукт для себя». Не MVP. Latency и стоимость — вторичны, первично качество рилса.
**Стек фиксирован:** Gemini (lite/flash-3), mlx-whisper + stable-ts + Deepgram, hevc_videotoolbox, Silero VAD, Moondream 2 GGUF.

---

## ✅ Tech-debt cleanup DONE (2026-04-19, 8 фаз, 10 коммитов)

- Phase 1 `36742e0` — subtitle sync hotfix (guard early write_ass при mutation path)
- Phase 2 `135be6d` — predictable reel count (floor/ceiling + Jaccard dedup)
- Phase 3 `c0af302 + 14855ca` — T6.1 cosine retrieval preference memory (Gemini embeddings + Alembic migration)
- Phase 4 `11f4c5d` — T9 composer strategy UI (radio + Cross-context badge + ReelPlan.cross_context_risk)
- Phase 5a `fd3c00f` — T8.1-T8.3 mouth sound detector + breath classifier + context-aware keep_sec
- Phase 5b `5ec3e96` — T8.4-T8.6 smart J/L chooser + adaptive leveller + preset switcher "Ручной монтаж"
- Phase 6 `a711321` — T2.8 screencast auto-zoom (cursor detector + spring planner + deictic layer)
- Phase 7a `4d5d251` — T3.1-T3.3 upload video preview + ClipScrubber/WaveformBar + ResultsFilters
- Phase 7b `ae92505` — T3.4-T3.7 CaptionsEditor + BrandKit + AspectPreview + ExportDialog
- Phase 7c `7806483` — T3.8-T3.10 hover-to-play + ScheduleButton + Instagram publisher (Graph API workflow)

Back-log (что осталось deferred для follow-up):
- FFmpeg applier для mouth_sound mute_zones (ProjectGraph frozen)
- adaptive_leveller FFmpeg volume filter integration
- screencast zoom merger в existing zoom_plan (ZoomKeyframe → ZoomCommand)
- BrandKit БД-backed persistence (сейчас LocalStorage)
- ExportDialog реальный transcode с preset bitrate
- Cursor templates в data/cursor_templates/*.png
- Instagram OAuth callback handler
- Full transcode с preset parameters в ExportDialog

Это рабочий tier-list. Каждая задача помечена `impact / effort / risk`. Пользователь выбирает что идёт в работу, в каком порядке. Задачи не стартуют автоматически.

---

## ✅ Что уже закрыто (чтобы не повторяться)

**Pipeline foundation:**
- TIER 1 quick wins (все 10): context caching, 2.5-flash-lite, disfluencies, acrossfade, hevc_videotoolbox hvc1, two-pass loudnorm, stable-ts MLX, Silero VAD, JSON schema, thinking budget
- TIER 2 core: semantic_chunker (gemini-embedding-001), filler removal, pause compression, J/L-cuts базовый, cross-chunk coherence validator
- Closure validator (trim-backward + forward extension)
- Cut snap к word-boundary (FEAT-#E, 30ms окно)
- **Subtitle resync после мутаций cuts (сегодня, 2026-04-19)** — устраняет дрейф субтитров к середине рилса

**Vision layer (6 фаз):** Moondream 2 GGUF, Visual Validator, Multimodal Dramaturgy, Smart Zoom, Cover Selector, Travel/B-roll.

**LLM infra:**
- Tier profiles: fast / legacy / balanced / quality + lite_variant (2_5 / 3_1)
- Runtime override через `/settings/performance`
- 2.5-flash-lite подтверждено как default — держит качество на structured tasks лучше Pro

**UX:**
- Dashboard: rename / list+grid view / checkbox bulk / thumbnails / nuke purge
- Stone-zen redesign (6 фаз)
- Profile editor /settings/profiles (5 профилей + custom)
- YouTube Shorts scheduler (OAuth2 + resumable upload + worker)

---

## 🔴 T0 — Критично: бьёт по ощущению качества прямо сейчас

Эти задачи стоят первыми, потому что пользователь уже ощущает их как боль.

### T0.1 — Концовки рилсов (closure quality) ✅ (2026-04-19)
**Сделано:**
- Semantic-aware strategy 3 в `closure_validator`: если ASR forward-terminator и backward-trim не находят closure, ищем ближайший `CanvasCandidateMoment` в forward-window [end_sec, end_sec+15s] с cosine(embedding, closure-query-embedding) ≥ 0.50. Если нашёлся — extend к его end.
- Closure-query pre-embed один раз на batch (переиспользуется для всех рилсов в job).
- Stats.closure_semantic_extended_count для диагностики в production.
- Требует canvas с populated embeddings (T1.1 slice 1 обеспечивает).
- Graceful-degrade: canvas=None или все embeddings=None → стратегии 1-2 как были.

**Связка с T1.1:** использует `CanvasCandidateMoment.embedding` + `cosine_similarity` + `embed_texts` из canvas_embedder.

`impact: HIGH | effort: 0.5д после T1.1 | risk: LOW`

### T0.2 — Coherence bugs backlog (job 9a38b907) ✅ (2026-04-19 — audit)
Все 4 бага уже закрыты в предыдущих коммитах (аудитом подтверждено 2026-04-19):
1. ✅ Single-segment reel guard — `coherence_validator.py:278-284` (`if len(segments) <= 1: return 1.0 "single-segment reel, coherence N/A"`)
2. ✅ Prompt recalibration — `prompts_data/coherence_check.md` (полностью переписан: anchor-примеры A-F, asymmetric caution, main_weakness опциональный, ожидаемый mean 0.70-0.78, спецкейсы для клиффхэнгеров/абстракций)
3. ✅ UI warning на high threshold — `PerformanceSettingsClient.tsx:834` ThresholdAdvice: warn при v>0.7, danger при v>0.8, recommendation зависит от mode.
4. ✅ Default threshold 0.5 — `runtime_settings.py:48` `Field(default=0.5, ge=0.0, le=1.0)`.

`impact: MEDIUM | effort: closed | risk: none`

### T0.3 — Stability: Next.js dev OOM на длинных job ✅ (2026-04-19)
**Симптом:** `next dev` падал через 1-2ч активного SSE+proxy трафика.
**Root cause:** Turbopack + HMR + live SSE + backend proxy кумулятивно тянут память.
**Сделано:**
- `package.json` dev script: `NODE_OPTIONS='--max-old-space-size=8192'` → V8 heap 4→8 GB запас для долгих сессий.
- `next.config.ts` experimental.preloadEntriesOnStart: false → отключает прогрев всех страниц при старте, начальный footprint меньше.
- Build gates: lint + tsc + build все clean (12 routes).

`impact: MEDIUM (UX, не ломает результат) | effort: 0.5ч | risk: none`

---

## 🧠 T1 — Три работы по памяти (архитектурное усиление pipeline)

Это ключевой инвестиционный блок. Усиливает всё downstream: концовки, дедуп, покрытие сцен.

### T1.1 — Semantic embeddings прикреплённые к Canvas (вариант A) ✅ (2026-04-19)
**Все 4 slice закрыты:**
- ✅ Infra slice 1/4 (`canvas_embedder.py` + поле `embedding` в `CanvasCandidateMoment` + интеграция в pipeline после Stage 5.2).
- ✅ Slice 2/4: Reducer hybrid-dedup (cosine ≥0.80 OR Jaccard ≥0.5 внутри 3s window). `EvidenceItem.embedding` + `_enrich_evidence_with_embeddings` + `_dedup_hybrid` + `_items_semantically_duplicate`. Legacy `_dedup_by_start_and_text` восстановлен как обёртка над hybrid для backward-compat.
- ✅ Slice 3/4: Story Doctor retrieval-augmented alternates. `RankedEvidenceItem.embedding` + `_build_embedding_index`/`_lookup_embedding` + `_augment_alternates_via_retrieval` (closure-query embed → cosine search по payoff-candidate items → top-3 AlternateSegment).
- ✅ Slice 4/4: Reels Composer cross-reel diversity. `_Candidate.avg_embedding` + `_populate_candidate_embeddings` + 3-уровневый `_greedy_uniqueness_filter` (overlap → semantic cosine ≥ 0.88 → Jaccard ≥ 0.65). Ловит рилсы с разным source-временем но одной мыслью разными сценами.

**Суть:** каждый `moment_id` в StoryCanvas получает embedding оригинальной фразы из транскрипта (не описания!). Downstream агенты получают semantic retrieval-способность.

**Что даёт:**
- **Reducer (Stage 6):** dedup по cosine similarity ≥0.85 вместо Jaccard по тексту описания. Текущий Jaccard ловит дубликаты-перефразировки слабо.
- **Story Doctor (Stage 7):** retrieval кандидатов на замену слабой концовки по query-embedding «завершающая мысль / круговая композиция».
- **Reels Composer:** может предпочесть momenты с высокой semantic distance в bookend-паре (начало ↔ конец рилса → эффект «раскрытия»).
- **Cross-reel diversity filter:** уже есть source-overlap filter (0.3 ratio), + semantic-overlap filter не даст выбрать рилсы с разной фразировкой но одной мыслью.

**Архитектура:**
- `gemini-embedding-001` (уже используется в `semantic_chunker`) — batch вызов после Stage 4 Canvas Builder.
- Добавить `embedding: list[float] | None` в `CanvasMoment` Pydantic-модель.
- Хранить как JSON-артефакт (`canvas_embeddings.json`), не в БД — артефакт reproducible.
- Опционально: `cosine_to(other_moment_id)` helper на Canvas для consumer'ов.

**Стоимость:** embedding ~$0.02 на видео, добавляет ~2с latency.

**Риски:** минимальные. Аддитивно, при `embedding=None` весь downstream работает как сейчас.

`impact: HIGH (closure + dedup + diversity) | effort: 1-2д | risk: LOW`

### T1.2 — Cross-visibility между агентами Stage 5 (вариант B) ✅ (2026-04-19)
**Progress 2026-04-19:**
- ✅ Slice 1: AgentConfig.wave split (wave 1 = hook/emotion/humor reaction-extractors; wave 2 = irony/thesis/motif meaning-extractors). Orchestrator `wave_execution=True` (default) запускает волны последовательно через барьер, внутри волны — параллелизм. `wave_execution=False` сохраняет legacy поведение для A/B.
- ✅ Slice 2: Детерминистический coverage_summary reducer (`services/extraction_coverage.py`) — собирает per-chunk count по hook/emotion/humor, gap-chunks, dominant themes, top strong fragments без LLM-вызова. Инжектится в user-payload волны 2 через новый `extra_user_context` параметр `run_extraction_agent`. `orchestrator` между волнами строит summary и передаёт в wave 2. Smoke: 3 evidence × 3 chunks → корректный gap [2], активные [0, 1], dominant_themes = [].
- ✅ Slice 3: Wave 2 промпты получают coverage_summary (покрыто slice 2 — `extra_user_context` = `coverage.to_prompt_text()` с явной задачей волны 2 «фокус на meaning-слое gap-chunks»).

**Суть:** 6 extract-агентов сейчас параллельны и слепы. Shared scratchpad между ними.

**Что даёт:**
- Ирония на границе эмоциональной сцены сейчас пропадает (emotion-агент взял, irony-агент не увидел).
- Дубликаты моментов через разных агентов — reducer фильтрует постфактум, грубо.
- Покрытие длинных видео: в 2.5ч видео агенты сходятся на первых 30% (где плотность выше) и пропускают финал.

**Архитектура (Map-Reduce-Map):**
- **Волна 1 (параллельно):** 3 агента (tension, emotion, quote) → выдают `draft_moments[]`.
- **Reducer между волнами (Flash Lite, дёшево):** даёт волне 2 `coverage_summary` — какие чанки уже покрыты, какие пустуют, какие типы моментов преобладают.
- **Волна 2 (параллельно):** 3 агента (irony, insight, hook) → получают coverage_summary в промпте, фокусируются на непокрытом.
- **Reducer Stage 6** объединяет обе волны как сейчас.

**Стоимость:** +15% latency Stage 5, +$0.003 на Flash Lite между волнами.

**Риски:**
- Если reducer между волнами ошибётся в summary — волна 2 получит плохой prior.
- Hard-coded split агентов 3+3 может быть неоптимален для разных профилей.

`impact: MEDIUM-HIGH (покрытие сцен) | effort: 3-4д | risk: MEDIUM`

**Зависимость:** можно сделать независимо от T1.1, но в связке с ним coverage_summary можно обогатить semantic cluster'ами (какие «темы» уже накрыты).

### T1.3 — Story Doctor ↔ Rhythm critique loop (вариант C) ✅ (2026-04-19)
**Сделано:**
- `story_doctor.compose_story_script(..., rhythm_critique: str | None = None)` — инжект критики в user payload при повторе.
- `pipeline._compose_with_rhythm_loop` — 2-iter loop: первый проход → check_rhythm → если < 0.60, собираем `_build_rhythm_critique` из `RhythmReport` и re-compose. Регрессия → выход, держим best-so-far. Max 2 итерации.
- Log `rhythm_critique_loop_start/result/exhausted` для production диагностики.
- Threshold `_RHYTHM_MIN_ACCEPTABLE = 0.60`, `_RHYTHM_MAX_ITERATIONS = 2`.
**Суть:** итеративная правка. Сейчас Story Doctor → Rhythm однонаправленно; если Rhythm ставит низкий score, ничего не происходит.

**Архитектура:**
- После Story Doctor → Rhythm.
- Если `rhythm_score < 0.6` → Story Doctor v2 получает Rhythm critique в промпте → повторная правка.
- Максимум 2 итерации (третья — redundant, Gemini начинает «лечить в обратную»).
- Если после 2 итераций всё ещё <0.6 → помечаем рилс `rhythm_warning=true` в артефакте, UI показывает badge.

**Стоимость:** +1 Story Doctor call на рилс в худшем случае (~$0.005 на рилс).

**Риски:**
- Зацикливание: Story Doctor в итерации 2 делает обратные правки к итерации 1. Митигировать через передачу `previous_version_hash` и запрет откатов.
- Сложность отладки: двойные прогоны → двойные логи, труднее понять почему вышло именно так.
- Может не дать заметного выигрыша, если проблема не в Story Doctor, а в Canvas.

`impact: MEDIUM | effort: 3-5д | risk: HIGH`

**Рекомендация порядка:** **T1.1 → T1.2 → (опционально) T1.3**. T1.1 самый дешёвый и самый прямой эффект на открытую боль T0.1. T1.2 даёт структурный апгрейд качества отбора. T1.3 — полируй только если после T1.1+T1.2 концовки всё ещё страдают.

---

## 🎬 T2 — Pipeline / quality

### T2.1 — Hierarchical Canvas ✅ частично (2026-04-19)
**Сделано (infrastructure + heuristic-builder):**
- `models/canvas.py`: новая модель `CanvasEpisode(id, time_range_sec, theme_ids, moment_ids, summary, duration_sec)`. `ProjectCanvas.episodes: list[CanvasEpisode]`.
- `canvas_builder._build_episodes_heuristic` — эвристическая группировка: bucket 10 мин, для source < 20 мин возвращает []. Distribute candidate_moments по start, собирает top-5 themes + top-3 one_liner как summary.
- Интеграция в `build_canvas` — после _parse_canvas_output canvas обогащается episodes.
- Log `canvas_built episodes=N`.

**Осталось (future slice):** подключение downstream consumers — агенты видят episode context вместо full canvas для длинных видео (optimization), thematic composer использует episode-boundaries для diversity (smoother rилсы).

`impact: HIGH для видео >1ч | effort: infrastructure done | risk: LOW`

### T2.2 — Cross-session preference memory ✅ (2026-04-19)
**Сделано:**
- `services/preference_memory.py`: `load_liked_anchors_text(artifact_store, current_job_id, max_anchors=8)` читает БД + reel_plan.json всех предыдущих job'ов, собирает top-8 лайкнутых hook'ов как few-shot anchors.
- `orchestrator.orchestrate_extraction(preference_anchors=...)` передаёт anchors в волну 1 через `extra_user_context`, в волну 2 — склеиваются с coverage_summary через `_combine_contexts`.
- `pipeline`: загружает anchors до orchestrate, передаёт через `_run_extraction_with_vision`. Graceful-degrade: exception → пустая строка.
- Log `preference_memory_loaded anchors_chars`.
- 0 LLM calls, только SQL + файловый I/O.
**Симптом:** пользователь лайкает/дизлайкает рилсы — LLM ничего не учится.
**Подход:** retrieve top-k лайкнутых рилсов, их moments → добавить как few-shot anchors в Stage 5 extract-промпты. Без fine-tune.

`impact: MEDIUM (накапливается со временем) | effort: 3-5д | risk: MEDIUM`

### T2.3 — Thematic composer ✅ (2026-04-19)
**Сделано:**
- `reels_composer._candidates_from_thematic_clusters`: union-find кластеризация `RankedEvidenceItem` по cosine ≥ 0.72 с inkrementally пересчитываемым centroid.
- Фильтр: кластер ≥ 3 items + hook + payoff. Body = top 1-2 peak/development не hook/payoff.
- Сборка ReelPlan в role-порядке (hook → body → payoff), а не chronology.
- Возвращает _Candidate(source="thematic_cluster") конкурирующий с другими через `_greedy_uniqueness_filter` (diversity + Jaccard + overlap).
- Graceful-degrade: <5 items с embedding → [].
- Константы: THRESHOLD 0.72, MIN_SIZE 3, MAX_CLUSTERS 20.

`impact: HIGH для fashion/lifestyle | effort: completed | risk: LOW`

### T2.4 — Real avg_score aggregation + real trend_score source ✅ частично (2026-04-19)
**Сделано:**
- `services/trend_lexicons.py` — per-profile trend лексиконы (talking_head / fashion / travel / screencast / custom) + universal viral markers (числовые hook'и, contrarian, intensifiers, personal revelation).
- `compute_trend_score(text, profile) -> 0..1` hit-rate на токенах hook + reasoning сегментов рилса.
- Интеграция в `_populate_reel_scoring`: `trend_pct` больше не константа 70, вычисляется per-reel. Baseline 0.5 для custom / пустых.
- Детерминистично, без LLM, O(words × lexicon).

**Также сделано (cycle 4):** real avg_composite_score через backend→frontend pipeline.
- `pipeline.py`: после `_populate_reel_scoring` считает `avg_composite_score` → analysis.stats → Job.options через `mark_done extra`.
- `models/job.py` JobRead: новое поле `avg_composite_score: float | None`, hoist из options.
- `api.ts`: JobRead type обновлён.
- `DashboardHero.tsx`: реальный avg из jobs с scored == "готово". 0 когда ни одной job со score (старые job'ы до T2.4 не учитываются).

`impact: MEDIUM | effort: completed (full) | risk: LOW`

### T2.5 — Rhythm-aware cutting (librosa beat detection) ✅ (2026-04-19)
**Сделано:**
- `services/beat_detector.py`: `detect_beats(audio_path) -> list[float]` async wrapper над `librosa.beat.beat_track`. Возвращает [] при failure / < 4 beats (вероятно talking_head без музыки).
- `snap_cuts_to_beats(cuts, beats, max_shift_sec=0.15)` → binary search ближайшего beat'а. Откат если snap ломает min duration.
- `runtime_settings.py`: `rhythm_aware_cuts_enabled` + `rhythm_aware_max_shift_sec` (0.15 default).
- `pipeline.py`: после cut_snap (word-boundary) второй snap к beat'ам. Переиспользует audio/source.wav.
- UI в PerformanceSettingsClient: SwitchRow + NumberRow под «Чистые срезы» группой.

**Auto-safe для talking_head**: detect_beats возвращает [] для non-percussive audio → snap = no-op.

`impact: HIGH для fashion/travel | effort: completed | risk: LOW`

### T2.6 — Match-cuts (perceptual hashing, без новых deps) ✅ (2026-04-19)
**Сделано (infrastructure + helpers):**
- `services/match_cuts.py` — aHash на PIL (уже в deps). Без PySceneDetect/imagehash — не требует установки.
- `compute_aash(image_path) -> int` 64-bit.
- `hamming_distance(a, b) -> int`, `visual_similarity(a, b) -> float`.
- `order_reels_by_visual_similarity(reel_ids, hashes_by_reel, start)` — жадный nearest-neighbor порядок для galerrейного режима. Unknown hashes (0) → в конец.
- Graceful-degrade: PIL exception → 0 hash → reel идёт в «unknown» ветку.

**Осталось (future UI):** подключить к frontend галерее — backend эндпоинт `/api/v1/jobs/{id}/gallery_order` использует `order_reels_by_visual_similarity` с aHash'ами thumbnail'ов рилсов.

`impact: MEDIUM | effort: infrastructure done | risk: LOW`

### T2.7 — Breath sound removal ✅ (2026-04-19)
**Сделано:**
- `runtime_settings.py`: `breath_compression_enabled` + `breath_compression_threshold_sec` (0.25 default, 0.15-0.5) + `breath_compression_keep_sec` (0.08 default, 0.03-0.2).
- `pipeline.py`: второй проход `compress_pauses_in_cuts` после pause_compression с breath параметрами. Использует тот же Silero VAD результат, переиспользует audio file.
- UI `PerformanceSettingsClient.tsx`: SwitchRow + 2 NumberRow под pause_compression, видно только когда pause включён.
- `api.ts` typed.

**ТРИЗ «унификация»:** не новый stage, а параметризация существующего. Breath compression — просто агрессивнее настроенный pause_compression. Всё ml-подобное (AEBSR arxiv) не требуется — Silero уже даёт достаточно точный VAD для коротких non-speech интервалов.

`impact: MEDIUM | effort: completed | risk: LOW`

---

### T2.8 — Screencast auto-zoom через cursor tracking (NEXT UP)
**Status:** ⏳ не начато. Research закрыт 2026-04-18 (`docs/screencast-zoom-research.md`).

**Что уже есть:** файл-заглушка `services/screencast_zoom.py` через Moondream `/detect cursor` — тупиковый подход (×50–500 медленнее template matching), нигде не вызывается, будет переписан.

**Цель:** для профиля `screencast` — автозум на курсор с плавным spring-сглаживанием + zoom-out во время пауз (как Screen Studio / Cap, лицензия MIT).

**Источник алгоритма:** [`pythonlearner1025/Screen-Studio-Effects`](https://github.com/pythonlearner1025/Screen-Studio-Effects) — Rust-порт ядра Cap. Портируем на Python.

**Slice 1/3 — Cursor detector (без Moondream):**
- OpenCV template matching по эталонным sprite курсора macOS/Windows/Linux (cache в `apps/backend/data/cursor_templates/`).
- Fallback: motion blob detection (diff между соседними кадрами + bounding box с малой площадью и высокой скоростью).
- Sampling каждые 33 мс (30 fps) — OpenCV template match ~5 мс/кадр CPU.
- Выход: `list[CursorEvent(x, y, t_sec, confidence)]`. Если confidence < threshold на > 60% кадров — считаем что это не скринкаст и отключаемся.
- API: `detect_cursor_events(video_path) -> list[CursorEvent]`.

**Slice 2/3 — Spring zoom planner (port of Screen-Studio-Effects):**
- Pipeline: `raw events → shake filter (median window 30ms) → densify → spring smoothing (damped harmonic oscillator ODE, аналитическое решение, frame-rate independent) → silence analysis (gap ≥ 0.5s + displacement < 2px) → auto-zoom segments`.
- Три damping-профиля: `underdamped` (для demo c быстрой динамикой), `critically_damped` (default), `overdamped` (для tutorial — плавнее).
- Выход: `list[ZoomKeyframe(t_sec, zoom_factor, center_x, center_y)]`.
- API: `plan_screencast_zoom(events, video_width, video_height, profile="critically_damped") -> list[ZoomKeyframe]`.

**Slice 3/3 — Integration + runtime settings + word-anchored layer:**
- `pipeline.py`: для profile=screencast вызов slice 1 + slice 2 → передача ZoomKeyframe в существующий `build_zoom_plan` / FFmpeg render.
- `runtime_settings.py`: `screencast_cursor_zoom_enabled` (default True для screencast, False для остальных), `screencast_damping_profile` (enum 3 варианта), `screencast_zoom_max_factor` (1.5-3.0, default 2.0).
- UI `PerformanceSettingsClient.tsx`: блок «Auto-zoom для скринкастов» (switch + profile selector + slider).
- **Word-anchored слой поверх** (работает на всех 5 профилях, не только screencast): whisper word-timing уже есть → лёгкий regex-pass по deictic-словам («вот», «здесь», «смотри», «тут») → добавляем zoom-in keyframes в моменты эмфазы. Не заменяет cursor-трекинг, а усиливает его. API: `inject_deictic_zoom_triggers(words_ts, existing_keyframes) -> list[ZoomKeyframe]`.
- Удалить `services/screencast_zoom.py` (Moondream-заглушка заменяется новой архитектурой).

**ТРИЗ:**
- «Использовать готовый ресурс»: алгоритм уже написан и отлажен в MIT-репо — портируем, не изобретаем.
- «Обратная связь через детект»: у нас нет event-stream курсора как у Screen Studio (пользователь даёт готовый `.mp4`) → синтезируем его через computer vision (template match). После синтеза алгоритм работает 1-в-1 как оригинал.
- «Graceful degrade»: если confidence cursor detector низкий → авто-отключаемся, профиль screencast рендерится без зума (не хуже чем сейчас).

**Зависимости:** +`opencv-python` (уже в deps проекта для других нужд — проверить, если нет, добавить). Moondream ОТКЛЮЧАЕМ на этой задаче. Librosa, PIL — переиспользуем.

**Acceptance:**
- Тестовый 5-мин скринкаст: курсор отслеживается с < 15 мс задержкой, zoom-in при активности, zoom-out при паузе > 0.5s без «рывков».
- Word-anchored layer: на фразе «вот смотри как работает X» вставляется zoom-in keyframe.
- Для не-screencast профилей ничего не меняется (guard по runtime_settings).

`impact: HIGH | effort: 5-7h | risk: LOW-MEDIUM`

---

## 🎨 T3 — Frontend / UX (handoff design implementation)

Сейчас реализовано ~15% handoff-дизайна. Осталось 85%:

### T3.1 — screen_workflow (полный upload flow)
Визуальная drag-drop с preview видео до запуска, встроенный стейдж-прогресс, профиль-selector с иконками.

`impact: HIGH (первый впечатление) | effort: 2-3д | risk: LOW`

### T3.2 — screen_clip (детальный просмотр рилса)
Timeline scrubber + text track + waveform + вариантные превью.

`impact: HIGH | effort: 3-4д | risk: MEDIUM`

### T3.3 — screen_results (grid-галерея)
Мультипросмотр, фильтры по virality/score/duration/profile, bulk actions.

`impact: MEDIUM | effort: 2-3д | risk: LOW`

### T3.4 — screen_captions (редактор субтитров)
Inline-правка текста, стилизации, timing-drag.

`impact: MEDIUM | effort: 4-5д | risk: MEDIUM`

### T3.5 — screen_brand (фирменные стили)
Сохранённые шрифты/цвета/лого для быстрого применения.

`impact: LOW-MEDIUM | effort: 2-3д | risk: LOW`

### T3.6 — screen_layout (аспект + позиционирование)
9:16 / 1:1 / 4:5 / 16:9 переключатели с preview. Manual crop override.

`impact: MEDIUM | effort: 2д | risk: LOW`

### T3.7 — screen_export (мультиплатформенный экспорт)
Пресеты TikTok/Reels/Shorts с правильными bitrate/LUFS, batch export.

`impact: MEDIUM | effort: 2д | risk: LOW`

### T3.8 — Reel preview inline video на dashboard
Hover-to-play mini-preview в JobCard.

`impact: MEDIUM | effort: 1д | risk: LOW`

### T3.9 — Schedule publication UI на ReelCard
Сейчас scheduler работает только через API. Кнопка «Опубликовать в…» с date-picker.

`impact: MEDIUM | effort: 1-2д | risk: LOW`

### T3.10 — Instagram Graph API
Блокер: Facebook App Review. Технически код готовности ~70%.

`impact: HIGH | effort: 1д кода + N недель review | risk: зависит от Meta`

---

## 🧪 T4 — Experimental / далёкий horizon

### T4.1 — OTIO export → DaVinci Resolve
Ручная доводка в Resolve после AI-раскадровки.

`impact: HIGH для power-users | effort: 3д | risk: LOW`

### T4.2 — B-roll auto-insert (Pexels + Gemini keywords)
Для travel/screencast профилей.

`impact: MEDIUM | effort: 5-7д | risk: MEDIUM`

### T4.3 — MPV EDL preview (zero re-encode)
Preview рилса до финального рендера через mpv + EDL.

`impact: MEDIUM (faster iteration) | effort: 2-3д | risk: LOW`

### T4.4 — ProRes intermediate для multi-pass
Для качественно-критичных финалов — сохранять ProRes mezzanine между stage-passes.

`impact: LOW (и так hevc_videotoolbox держит качество) | effort: 2д | risk: LOW`

### T4.5 — Gemini 3.1 Flash Lite 1M context collapse
Когда stable выйдет — collapse 9-stage pipeline в один structured-output call. Проектировать изменения с этим прицелом.

`impact: MASSIVE | effort: 2-3 недели | risk: зависит от API stability`

---

## 🔧 Недостающие ручки во фронте (backlog 2026-04-19)

После Ralph Loop циклов 1-12 backend имеет новые runtime_settings поля,
но `/settings/performance` UI их **НЕ показывает**. Для Manual mode
пользователь не может их настроить через фронт.

Нужно добавить controls в `PerformanceSettingsClient.tsx`:

**Snap strategy (T10.2):**
- `snap_strategy` enum — select/radio (beat / onset / both / off)
- `onset_snap_max_shift_sec` — NumberRow 0.02-0.2, step 0.01

**Pipeline mode (T11):**
- `pipeline_mode` enum — radio (manual / automatic) с пояснениями

**Pacing profile (T10.5):**
- `pacing_profile` enum — radio/select (dynamic / balanced / mkbhd_clean / documentary)

**Punchline pause (T10.1):**
- `punchline_pause_enabled` — SwitchRow
- `punchline_pitch_drop_hz` — NumberRow 5-60, step 1
- `punchline_hold_after_sec` — NumberRow 0.1-1.0, step 0.05

**Punch-in zoom (T10.3):**
- `punch_in_zoom_enabled` — SwitchRow
- `punch_in_zoom_scale` — NumberRow 1.0-1.15, step 0.01
- `punch_in_zoom_probability` — NumberRow 0-1, step 0.05
- `punch_in_zoom_hold_ms` — NumberRow 200-1500, step 50

**Ken Burns drift (T10.7):**
- `ken_burns_drift_enabled` — SwitchRow
- `ken_burns_scale_per_sec` — NumberRow 0.001-0.01, step 0.0005
- `ken_burns_max_scale` — NumberRow 1.005-1.05, step 0.005

**api.ts PerformanceSettings interface** — дополнить соответствующими
полями (сейчас backend вернёт extra fields, frontend type не видит).

**Расчётное время:** ~15-20 мин моего времени. Следующий цикл интеграции.

---

## 🛡️ Auto Mode boundaries (фиксация 2026-04-19, дополнение)

Пользователь явно зафиксировал что Auto mode **не трогает** (вот полный список):
- **LLM model** — всегда `gemini-2.5-flash-lite`. Проверено: advisor не меняет `llm_tier_profile/llm_model/llm_lite_variant`. Если когда-то Auto начнёт менять — считать регрессией и убирать.
- **Aspect ratio** — user выбирает через UploadWizard (9:16 / 1:1 / 4:5 / 16:9)
- **fit_mode** — user выбирает (fill / fit)
- **Moondream vision enabled** — user тумблером
- **Zoom on/off** — user решает (post_production `zoom_enabled`). ⚠ Punch-in zoom и Ken Burns — это subset zoom effects, должны respect zoom master toggle
- **Intro on/off** — user решает (intro_path не пусто = on). UI toggle + optional preset selector
- **Чёрно-белый режим on/off** — user решает (bw effect в video_effects tuple)

Auto mode **полностью автоматизирует всё остальное**:
- Склейки: snap_strategy, rhythm_aware, J/L-cuts, transition choice, match-cut
- Звук: pause/breath compression, filler removal, punchline pause, adaptive leveling
- Постпродакшн внутри разрешённых toggle'ов: punch-in zoom и Ken Burns только если zoom_enabled=True, интенсивность subtitle styling
- Pacing: pacing_profile template
- Composer: composer_strategy + cross-context penalty + coherence threshold

**Иерархия toggle'ов:** Master user toggle (zoom/intro/bw) → если off, Auto mode НЕ включает sub-features этой категории даже если sample говорит что надо.

---

## 🐞 BUG — Subtitle sync regression (2026-04-19)

После циклов T10/T11 интеграции user видит что субтитры снова слетают. Вероятный корень:
- **punchline pause extension** (`speech: list[SpeechSegment]` мутируется до compression) может сдвигать final cuts на `hold_sec` (до 0.55 сек). ASS-файлы генерятся ДО этой мутации.
- **motion_filter_expr (zoompan)** — не меняет длительности, только scale, субтитры должны быть ok.
- **J/L-cut** (TIER2-#15) — уже имеет ASS resync.

**План расследования:**
1. Проверить где именно строятся ASS subtitles (`subtitles.py` + `pipeline.py:write_ass` вызовы) — BEFORE или AFTER pause_compression?
2. Если BEFORE — после punchline extension → compression результат cuts смещён → subtitles неверны.
3. Решение: либо ресинк ASS после всех мутаций (pause + breath + punchline + filler + snap), либо переместить генерацию ASS после всех stage'ов.
4. Тест на реальном видео с punchline_pause_enabled=True.

**Priority:** HIGH — качество финальных рилсов ломается.

---

## 🎛️ Frontend control plan (2026-04-19)

User: «во фронте не увидел новых ручек настроек от всего что было добавлено это тоже запиши в правки... выводим все ручки во фронт-энд все должны крутиться. Должны быть рекомендации по стандартам».

**Требования:**
1. **Все runtime_settings → controls в `/settings/performance`** (Manual mode), включая новые T10/T11 поля (snap_strategy, pacing_profile, punchline_pause, punch_in_zoom, ken_burns, pipeline_mode).
2. **Рекомендации по каждой ручке** — показать рядом с контролом «Стандарт: 0.45с для talking-head» / «Рекомендовано: 1.06x» (текстовая подсказка или badge с default значением).
3. **Reset to default** — кнопка «Вернуть стандарт» на каждой группе.
4. **Иерархия master/child toggles:**
   - Zoom master toggle + {punch_in_zoom_enabled, ken_burns_drift_enabled} — child ручки disabled если master off
   - Pause compression master + {punchline_pause_enabled} — child зависит от master
5. **User-controlled boundaries UI** — отдельная секция «Основные параметры» с zoom/intro/bw/LLM/aspect/fit toggle + select, подписанная «Auto mode эти параметры не трогает»
6. **api.ts** — расширить PerformanceSettings interface всеми новыми полями (сейчас типы не включают 14+ новых runtime_settings fields).

**Файлы для модификации:**
- `apps/frontend/src/components/PerformanceSettingsClient.tsx` — добавить секции
- `apps/frontend/src/lib/api.ts` — расширить PerformanceSettings
- `apps/frontend/src/components/upload/UploadWizard.tsx` — добавить zoom/intro/bw master toggle если их там ещё нет

**Рекомендации по стандартам (default values и их обоснование для UI):**

| Параметр | Стандарт | Источник |
|---|---|---|
| snap_strategy | onset | talking-head default; beat/both при музыке |
| onset_snap_max_shift_sec | 0.08 | research editing-craft §6 |
| punchline_pitch_drop_hz | 20 | research §1.5 Parselmouth baseline |
| punchline_hold_after_sec | 0.45 | MovieCuts dataset + MKBHD analysis |
| punch_in_zoom_scale | 1.06 | research §4 natural feel, max 1.15 |
| punch_in_zoom_probability | 0.3 | 30% emphasis moments (research default) |
| punch_in_zoom_hold_ms | 500 | research §4 ms @ 30fps |
| ken_burns_scale_per_sec | 0.003 | 0.3% per sec = invisible drift |
| ken_burns_max_scale | 1.025 | за 8+ сек шота → 2.5% max |
| pacing_profile | balanced | middle ground; dynamic для energy, documentary для обучающего |
| pipeline_mode | automatic | default Auto (user может переключить) |
| coherence_threshold | 0.5 | normal pitch baseline |

**Расчётное время на реализацию:** ~20-25 мин моего времени.

---

## 🛡️ Auto Mode boundaries (legacy — до обновления 2026-04-19)

---

## 🤖 T11 — Automatic Mode (робот-монтажёр)

**Главная фича** (пользователь 2026-04-19):

> «Я откинул видео, он его проанализирую и принимает решение по всем функциям — какие включаются, какие не включаются, какие паузы делаются, на каких участках, динамически, правильным образом. Просто робот.»

**Это ключевая фича для достижения target «100% замена монтажёра».** Система сама анализирует загруженную дорожку, решает какие features pipeline включать/выключать, какие threshold'ы ставить, где какие паузы удерживать, какой pacing profile применять.

**Manual Mode остаётся** для power-user'ов которые хотят ручной контроль.
**Default = Automatic.**

### Research закрыт 2026-04-19

Полный отчёт: `docs/research/automatic-mode-2026.md` (75K токенов, 25 tool uses).

**Главный вывод:** hybrid **rule tree + LLM fallback** архитектура. **85-90% автономности** для typical talking-head на русском/английском через rule tree (без training data). Gemini Flash Lite для low-confidence cases. Feedback loop для будущего ML classifier через T6.

**Что меняется от моего черновика:**
- Не «Audio Feature Extractor + Hybrid Rule Engine» абстрактно — а **25 конкретных правил** в таблице Feature→Decision→Parameter
- Не абстрактный «classifier» — а **sklearn MLPClassifier** после 200+ решений (weekly batch retrain)
- Не просто «LLM fallback» — а **confidence<0.4 threshold** с Gemini Flash Lite
- Per-chunk через **existing infrastructure** (Stage 2 compression уже даёт chunks)

### Архитектура (черновик, уточнится после research)

**Новый service:** `services/auto_config_advisor.py`

```python
async def analyze_and_configure(
    audio_path: Path,
    transcript: TranscriptResult,
    canvas: ProjectCanvas | None,
    base_profile: VisionProfile,
) -> PerformanceSettings:
    """
    Анализирует видео и возвращает optimal PerformanceSettings для этого
    конкретного файла. Используется вместо глобальных defaults в Auto Mode.
    """
```

**Стадии:**

**T11.1 — Audio Feature Extractor:**
- SNR estimation (librosa + noise floor estimation)
- Speaker rate (whisper words / duration)
- Pitch variance (Parselmouth F0 std)
- Loudness range (pyloudnorm LRA)
- Spectral centroid stability (librosa)
- Pause distribution stats (mean/std/kurtosis gaps между whisper segments)
- Prosody rhythm regularity (onset times variance)
- Scene stability (Moondream face tracking confidence variance)

**T11.2 — Decision Engine (Hybrid — rule tree + LLM fallback):**

Быстрые решения — детерминистический rule tree:
```python
if snr_db < 15: settings.noise_reduction_enabled = True
if speaker_rate > 3.5: settings.pacing_profile = "dynamic"
if speaker_rate < 2.0: settings.pacing_profile = "documentary"
if pitch_variance > 120: settings.punch_in_probability = 0.4
if pitch_variance < 60: settings.punch_in_probability = 0.15
if lra > 14: settings.adaptive_leveling_enabled = True
if pause_std > 0.8: settings.pause_compression_aggressive = True
```

Сложные решения (narrative-level) — Gemini Flash Lite prompt:
```
Вот metrics аудио: {features}
Вот transcript summary: {canvas_summary}
Реши:
- snap_strategy: beat | onset | both | off
- composer_strategy: tight | balanced | thematic_free
- coherence_threshold: 0.4-0.7
- punchline_hold_sec: 0.3-0.6
Верни JSON.
```

**T11.3 — Confidence Scorer:**
Каждое решение помечается `confidence: low | medium | high`. Low confidence → fallback на conservative defaults текущего profile.

**T11.4 — Per-Chunk Zone Adjustments:**
Если видео спанает разные zones (интро / разговор / CTA) — per-chunk feature re-extraction, per-chunk settings override. Для рилса спанающего несколько zones — weighted average.

**T11.5 — UI integration:**
- Upload wizard: toggle «Auto / Manual» (default Auto).
- Если Auto: после анализа показать `AutoConfigSummary` — «Система решила: dynamic pacing, 40% punch-in zoom, punchline hold 0.45s, snap_strategy=onset, composer=balanced. Запустить?»
- Button «Override отдельные параметры» — expandable list.
- Auto-saved config template: «Мой подход для этого типа видео» после одобрения.

**T11.6 — Learning loop (с T6):**
После каждого лайкнутого рилса — записать (audio_features, chosen_settings) → (liked: bool). После 20+ пар — шаблон переобучается через logistic regression на (features → best settings).

### Связь с T10

T10 реализует **сами features** (punchline pause, onset snap, punch-in zoom, variable duration).
T11 решает **когда какую feature включать и с какими параметрами** для конкретного видео.

**T10 без T11 = manual mode с runtime_settings.**
**T10 + T11 = полная автономность (робот-монтажёр).**

### ТРИЗ
- «Отделить механизм от решения»: T10 — механизмы, T11 — policy layer сверху.
- «Re-use existing telemetry»: все features которые Audio Feature Extractor вычисляет — уже частично считаются в pipeline (whisper word stats, librosa VAD, Parselmouth для T10.1). Нужна только агрегация.
- «Progressive autonomy»: старт с hard rule tree → постепенное добавление LLM-решений → постепенное учение на лайках.

### Новые зависимости (все MIT/Apache/BSD, без GPU)

```toml
[project.dependencies]
# librosa, silero-vad — уже есть
"opensmile>=2.5.0",           # eGeMAPSv02 88 features
"praat-parselmouth>=0.4.3",   # pitch, HNR (GPL-3)
"pyloudnorm>=0.1.1",          # EBU R128 LRA
"noisereduce>=3.0.0",         # spectral gating
"pedalboard>=0.9.22",         # NoiseGate, Compressor (GPL-3, Spotify)
"scikit-maad>=1.5.1",         # temporal_snr() 3 строки
```

**Note:** Parselmouth и pedalboard — GPL-3. Для public SaaS это ограничивает лицензирование. Для приватного использования (2-3 пользователя) — ок.

### 25 параметров pipeline — полная матрица правил

См. `automatic-mode-2026.md` секция B (Feature → Decision → Parameter таблица).

**Ключевая pacing_profile матрица (WPS × pitch_std):**

```
              WPS
       <2.0   2-2.8  2.8-3.5  >3.5
     ┌──────┬──────┬────────┬───────┐
pit  │ doc  │ bal  │  bal   │ dyn   │  >40 Hz
std  │ doc  │ bal  │ mkbhd  │ dyn   │  20-40
     │ doc  │ doc  │ mkbhd  │ mkbhd │  <20
     └──────┴──────┴────────┴───────┘
```

### Latency targets (из research)

| Этап | Время |
|---|---|
| Feature extraction (параллельно) | <15 сек для видео до 60 мин |
| Rule tree evaluation | <100 мс |
| LLM fallback (Gemini Flash Lite) | 2-5 сек |
| **UI to user total** | **<20 сек от Upload клика** |

Pitch через Parselmouth — самый медленный (~12 сек для 30-мин видео). Он определяет нижнюю границу параллельного времени.

### Safety limits (обязательно)

```python
SAFETY_LIMITS = {
    "pause_compression_keep_sec": {"min": 0.15, "max": 0.5},
    "breath_compression_keep_sec": {"min": 0.08, "max": 0.25},
    "punch_in_zoom_intensity": {"min": 1.0, "max": 1.20},
    "max_shift_sec": {"min": 0.0, "max": 0.5},
    "coherence_threshold": {"min": 0.3, "max": 0.8},
}
```

### UI Summary Card (обязательно)

После анализа — показать что система решила, с confidence %, до того как pipeline запустится. User может override или нажать «Запустить».

### Реальные сроки (калибровка ×7)

- T11.1 Audio Feature Extractor (параллельный asyncio + 7 libs) — **~8 мин**
- T11.2 Hard Rule Engine (25 правил + safety limits) — **~12 мин**
- T11.3 Confidence scorer + fallback — **~5 мин**
- T11.4 UI toggle + Summary Card (frontend) — **~7 мин**
- T11.5 LLM advisor (Gemini Flash Lite для narrative) — **~7 мин**
- T11.6 Per-chunk zones + weighted merge — **~8 мин**
- T11.7 DB schema AutoModeDecision + feedback collection — **~6 мин**
- T11.8 Learning loop с T6 (когда T6 созреет) — **~15 мин**

**Итого T11 MVP (T11.1-T11.5): ~40 мин моего времени**
**T11 полный (без learning loop): ~55 мин**

`impact: MAX (ключевая фича для «замены монтажёра») | effort: ~40 мин MVP / ~55 мин полный | risk: MEDIUM (safety limits + warnings обязательны)`

---

## 🎬 T10 — Editing craft (полная замена монтажёра)

**Главная рамка** (пользователь 2026-04-19, уточнено):

> «Мы стремимся полностью заменить монтажёра рилсов — получать сильные рилсы в полностью автономном режиме. Приоритет: talking_head → screencast → дальнейшее развитие.»

**НЕ «60% помощь монтажёру», а 100% автономность.** Цель — робот-монтажёр, выдающий финальный рилс без human review. Дальний этап: добавление музыки с регулировкой громкости и синхронизацией битов.

**Обязательные архитектурные правила для всех T10.x:**
1. **Каждая функция = runtime_settings toggle on/off + intensity** (манифест 2026-04-19).
2. **Legacy не удаляем.** T2.5 librosa beat-snap СОХРАНЯЕТСЯ как опция (`snap_strategy: beat | onset | both`) — beats понадобятся когда добавим музыку.
3. **Default = автоматический режим** (T11), manual — power-user override.

**Research закрыт 2026-04-19** — `docs/research/editing-craft-2026.md` (полный отчёт). Главный вывод: **ни один mass-market AI editor (Opus Clip, Descript, Gling, Vizard) не управляет variable pacing внутри одного рилса в 2026**. Все решают «что включить», но не «как быстро резать в разных частях». **Это прямая точка роста для videomaker.**

### Фундамент — Walter Murch Rule of Six (приоритет при резке)

| Priority | Параметр | Вес | Статус у нас |
|---|---|---|---|
| 1 | **Emotion** | **51%** | Частично (sentiment + energy spikes) |
| 2 | Story | 23% | Частично (LLM narrative Stage 7) |
| 3 | Rhythm | 10% | T2.5 beat-snap (базово) |
| 4 | Eye Trace | 7% | Нет (T10.6 добавит) |
| 5 | 2D Space | 5% | Face tracking есть |
| 6 | 3D Space | 4% | Не автоматизируется |

**Вывод:** emotion должен быть primary signal. Сейчас у нас rhythm weighted ≈ 25%, emotion ≈ 15% — нужна rebalance.

### TOP-5 задач (priority от research по effort/impact)

#### T10.1 — Punchline Pause Detection (Effort: S, Impact: HIGH) ⭐ RECOMMEND FIRST

**Задача:** после punchline (pitch final lowering > 20 Hz drop в последние 0.3 сек segment'а) — удержать паузу 0.35-0.55 сек перед cut.

**Почему:** один из самых заметных признаков ручного монтажа. Алгоритмы сжимают все паузы — monteur «даёт осесть» тезису. Разрешимо через Parselmouth pitch analysis.

**Зависимости:** Parselmouth 0.4.7 (MIT, Python Praat wrapper — новая зависимость, ~5 MB).
**Интеграция:** Stage 3 compression — не сжимать паузы после punchline_moments. Stage 8 rhythm check учитывает punchline_hold_frames.

#### T10.2 — Prosody-Aware Cut Snapping (S, HIGH) ⭐ ПАРАЛЛЕЛЬНО с T2.5, не замена

**Задача:** **ДОБАВИТЬ** onset-snap (±0.08 сек к speech onsets через `librosa.onset.onset_detect`) **параллельно** существующему beat-snap (T2.5, librosa beat_track ±0.15 сек).

**Runtime setting:** `snap_strategy: beat | onset | both | off` (enum, default = `onset`).
- `beat` — текущий T2.5 (нужен для будущего добавления музыки с регулярным ритмом)
- `onset` — новый (для talking-head без music)
- `both` — сначала onset если найден, fallback beat
- `off` — без snap (hard cuts)

**Почему `both` вариант:** если пользователь потом добавит музыку в будущем, beats снова станут релевантны. Не удаляем ни один code path.

**Зависимости:** librosa уже есть. Никаких новых deps.
**Интеграция:** дополнить `beat_detector.py` функцией `detect_onsets`, рядом с `detect_beats`. `snap_cuts_to_beats` → обобщить в `snap_cuts_to_reference(cuts, reference_times, max_shift_sec)`. Strategy resolver выбирает reference_times по runtime_settings.

**Время реализации: ~20 мин моего времени.**

#### T10.3 — Punch-In Zoom на Stressed Syllables (S, HIGH) ⭐ UPGRADE T2.1

**Задача:** на каждом stressed syllable (Parselmouth intensity peak > mean + 0.5*std) — subtle punch-in zoom.

**Numerical rules:**
- Вход: 1.00x → 1.06x за 5 кадров (167мс @ 30fps, ease-out)
- Hold: 15 кадров (500мс на пике)
- Выход: 10 кадров (333мс, ease-in)
- Max zoom для natural feel: 1.15x (больше → cartoonish)
- Probability: 30% от ключевых моментов (не все подряд)

**Почему:** то что монтажёр делает вручную в DaVinci/Premiere keyframe scale. Зритель не осознаёт zoom, но чувствует emphasis.

**Зависимости:** FFmpeg zoompan filter (есть). Parselmouth для stress detection.
**Интеграция:** `services/zoom_planner.py` — новый source `stressed_syllable_source` плюс к existing `face_tracking_source`.

#### T10.4 — Variable Shot Duration by Emotion (M, HIGH)

**Задача:** сегменты рилса получают разную длительность по energy score:

| Energy range | Target duration |
|---|---|
| 0.0-0.3 (low) | 3.5 сек |
| 0.3-0.6 (medium) | 2.5 сек |
| 0.6-0.8 (high) | 1.8 сек |
| 0.8-1.0 (peak) | 1.2 сек |

**Сигналы energy:** OpenSMILE loudness_sma3 + pitch variance + LLM sentiment (уже считается Stage 4).

**Интеграция:** `reels_composer.py` — при scoring кандидатов учитывать target_duration, penalизовать рилс если variance shot duration близка к нулю (flat pacing).

#### T10.5 — Pacing Profile + Consistency Engine (M, HIGH)

**Задача:** Pacing Profile templates на уровне profile (talking_head / fashion / travel / screencast / custom) + user override. Гарантирует что все рилсы job'а имеют одинаковый почерк.

**Шаблоны (из research):**
```python
DEFAULT_PACING_PROFILES = {
    "dynamic": {           # high-energy content
        "shot_duration_mode": 1.8, "shot_duration_max": 4.0,
        "punch_in_rate": 0.4, "transition_hard_cut_ratio": 0.85,
    },
    "documentary": {       # обучающий content
        "shot_duration_mode": 3.5, "shot_duration_max": 8.0,
        "punch_in_rate": 0.15, "punchline_hold": 0.5,
        "transition_hard_cut_ratio": 0.70,
    },
    "mkbhd_clean": {       # tech review style
        "shot_duration_mode": 2.8, "punchline_hold": 0.4,
        "punch_in_rate": 0.2, "transition_hard_cut_ratio": 0.95,
    }
}
```

**Ссылка на T6:** после 5-10 одобренных рилсов — Bayesian update профиля → персонализированный почерк.

### Остальные задачи (не top-5, но нужны)

**T10.6 — Smart transition chooser:**
- Новый stage: для каждой границы решает hard/J/L/dissolve/match-cut
- Триггеры из research (MovieCuts dataset 2022):
  - Смена speaker → J-cut 0.25-0.35 сек (28% случаев)
  - Конец `?` риторический → L-cut 0.20-0.30 сек
  - Смена темы → J-cut 0.30-0.45 сек
  - Эмоциональный пик → L-cut 0.25-0.40 сек (19%)
  - Конец `.` → Hard cut 0.05-0.10 сек
  - Same-frame visual similarity по aHash (T2.6) → match-cut
- AutoTransition++ dataset (V-Trans4Style, MIT) — как reference, но rule-based реализация проще

**T10.7 — Ken Burns drift для statical shots:**
- Slow drift 0.3-0.5% scale per second
- За 5 сек шота: 1.00x → 1.025x
- Направление к лицу/объекту (T2.1 уже даёт центр)
- Effort XS, Impact MEDIUM — одна ffmpeg zoompan команда

**T10.8 — Eye trace continuity (MediaPipe iris):**
- Gaze direction разница > 0.3 между концом A и началом B → penalty в composer
- Optical flow cosine similarity на последних 5 frames A и первых 5 B
- Integrate as scoring signal в T9 balanced mode

**T10.9 — Cross-Context Risk Score:**
- Semantic similarity < 0.4 → risk flag
- Temporal gap > 5 мин → требует narrative justification от LLM
- Sentiment reversal от одного speaker → high-risk flag
- UI warning badge в ReelCard «Cross-context detected — проверьте перед публикацией»

### Полный набор numerical constants (для реализации)

```python
EDITING_CRAFT_CONSTANTS = {
    "min_shot_duration": 1.2,
    "max_shot_duration": 6.0,
    "default_duration": 2.5,
    "punchline_hold_after_sec": 0.45,
    "question_hold_sec": 0.6,
    "onset_snap_window_sec": 0.08,
    "beat_snap_window_sec": 0.15,       # legacy для music
    "punch_in_zoom_scale": 1.06,
    "punch_in_frames": 5,               # 167мс @ 30fps
    "punch_in_hold_frames": 15,         # 500мс
    "punch_out_frames": 10,             # 333мс
    "punch_in_probability": 0.30,
    "ken_burns_scale_per_frame": 0.0003,
    "ken_burns_max_scale": 1.025,
    "j_cut_offset_sec": 0.3,
    "l_cut_offset_sec": 0.3,
    "cross_dissolve_duration_sec": 0.4,
    "dip_to_black_duration_sec": 0.5,
    "high_energy_threshold": 0.65,
    "low_energy_threshold": 0.35,
    "semantic_similarity_min": 0.4,
    "temporal_gap_risk_sec": 300,       # 5 мин
    "sentiment_shift_threshold": 0.5,
}
```

### ТРИЗ

- **«Не заменять, а слои накладывать»:** T2.3 даёт кандидатов → T10 делает их monteur-grade (pacing + transitions + motion + consistency)
- **«Detect с existing data»:** whisper prosody, Moondream face positions, librosa — всё уже считается. Только decision layers поверх.
- **«Priority по Murch»:** emotion (51%) → primary scorer, rhythm (10%) → snap layer.
- **«Template + user override»:** Pacing Profile default per profile, power-user меняет под свой почерк.

### Границы автоматизации (из research)

1. **Emotion as primary editorial judgment** — machine не понимает narrative rightness напрямую, но **через T11 Automatic Mode** система принимает решения по сигналам (pitch, energy, sentiment) — приближение к 100% автономности.
2. **Намеренная imperfection (Casey style)** — не наш target. Мы делаем clean production style (MKBHD-like + punchy reels).
3. **Conceptual match-cuts** (Kubrick bone → space station) — оставляем ручным power-user feature.
4. **Breathability на macro-arc** — решается через Pacing Profile (T10.5) + Story Doctor narrative arc (существует).
5. **Real-time адаптация к аудитории** — offline через T6 preference learning на лайках.

**Отличие от default research вывода:** research рекомендовал «60% auto + human review». **У нас другой target — 100% auto через T11.** Не оставляем узких мест требующих ручной проверки.

### Порядок реализации (calibrated time)

**Quick wins блок (~90 мин реального времени):**
- T10.1 Punchline Pause Detection — ~25 мин
- T10.2 Prosody Onset Snap (параллельно T2.5) — ~20 мин
- T10.3 Punch-In Zoom upgrade T2.1 — ~30 мин
- T10.7 Ken Burns drift — ~15 мин

**Medium блок (~3 часа):**
- T10.4 Variable Shot Duration — ~60 мин
- T10.5 Pacing Profile Templates + runtime_settings — ~45 мин
- T10.6 Smart transition chooser — ~60 мин
- T10.8 Eye trace continuity (MediaPipe) — ~40 мин
- T10.9 Cross-Context Risk Score — ~30 мин

**Все с toggle on/off в runtime_settings.** Default — включены в Automatic Mode (T11), выключены в Manual Mode с ручной настройкой.

### Связь с другими блоками

- **T8** (audio cleanup) — ~30% craft'а, живёт параллельно
- **T9** (composer mode) — context-awareness, пересекается с T10.9
- **T6** (preference ML) — когда созреет, T10.5 становится per-user learned
- **T2.5** (rhythm-aware) — заменяется T10.2
- **T2.1** (zoom_planner) — расширяется T10.3
- **T2.6** (aHash) — используется T10.6 (match-cut trigger)

### Зависимости (новые)

- **Parselmouth 0.4.7** (MIT) — pitch/intensity для punchline + stress detection
- **OpenSMILE Python** (Apache-2.0) — energy features для variable duration
- **MediaPipe Face Mesh** (Apache-2.0) — iris tracking для eye trace (T10.8 only)
- **moviepy 2.2.1+** (MIT) — speed ramp и J/L-cut rendering (T10.6 only)

Без GPU, всё CPU. Все MIT/Apache-2.0.

`impact: MAX (ключевая жалоба пользователя) | effort: 3 недели для полного T10, 2 дня для top-4 quick wins | risk: MEDIUM (slotted в существующую архитектуру, каждая фича с toggle)`

---

## 🎙️ T8 — Adaptive audio editing (как ручной монтаж)

**Проблема пользователя (2026-04-19):** текущие глобальные threshold'ы (pause 0.25s, breath 0.2s, filler list, keep_sec 0.08) не адаптируются к неровной записи:
- Микрофон ловит разно в разных местах видео → один threshold не подходит
- Speaker сглатывает концы слов где-то — а где-то нет → pipeline либо «съедает слово», либо оставляет «цоканье»
- Цель: «как будто человек сидел и резал вручную» — гибкие J/L-cuts разной длины, адаптивная пауза «дыхания» в зависимости от контекста (точка vs запятая vs смена темы)

**Research запущен 2026-04-19** (deep-research-analyst) — ищет конкретные библиотеки 2026. Полный отчёт попадёт в `docs/research/adaptive-audio-editing-2026.md`.

### Направления research (что изучает агент)

1. **Click/pop/lip-smack detection** — open-source альтернативы iZotope RX. Meta Demucs, Facebook Denoiser, DeepFilterNet, `noisereduce` — что умеет классифицировать mouth sounds.
2. **Adaptive breath detection** — не просто VAD, а классификатор «вдох vs тишина vs пауза». AEBSR (arxiv), wav2vec2-based breath models на HuggingFace.
3. **Adaptive loudness levelling** — open-source альтернативы Auphonic Adaptive Leveler. Per-segment gain adjustment vs global EBU R128.
4. **Dropped word endings detection** — whisper word-level confidence + envelope decay analysis → маркировать «articulation cut» vs «bad mic».
5. **Context-aware pause retention** — keep_sec зависит от punctuation (точка > запятая > продолжение мысли), от position в рилсе (начало/середина/конец), от следующего cut type (hard/J/L).
6. **J/L-cut rules** — индустриальные правила когда делать offset (0.2 / 0.35 / 0.5 сек). Смена speaker, риторическая пауза, смена темы.
7. **Prosody features** — OpenSMILE, pyAudioAnalysis — связать pitch/intonation с cut-length variation.

### План реализации (черновик, уточнится после research)

**T8.1 — Mouth-sound detector:**
- Интеграция detector → маркирует проблемные зоны (clicks, lip-smacks, cluck) перед composer
- Output: `list[AudioDefect(type, start_ms, end_ms, confidence)]` → composer avoid-zones + render filter
- Graceful degrade: если модель fail → текущее поведение

**T8.2 — Adaptive silence/breath classifier:**
- Замена глобального Silero VAD + breath threshold на per-segment классификатор
- Модель: TBD после research (возможно Silero VAD fine-tuned или wav2vec2 downstream head)
- Per-segment noise floor estimation — calibration по первым N секундам каждого chunk

**T8.3 — Context-aware keep_sec:**
- Punctuation-driven retention: точка → 0.25s, запятая → 0.12s, внутри предложения → 0.06s
- Использует whisper-large-v3 punctuation (уже есть)
- Runtime setting: «manual threshold» vs «adaptive» режим

**T8.4 — Smart J/L-cut planner:**
- Новый stage между pause_compression и render: решает для каждого cut boundary — hard / J (audio early) / L (audio late)
- Эвристики на основе: speaker continuity, punctuation context, rhythm snapping (T2.5 уже есть)
- FFmpeg cmd generation с offset'ами для audio streams

**T8.5 — Adaptive loudness leveller:**
- Per-segment gain normalization до render
- Замена глобального loudnorm на envelope-aware processing

**T8.6 — UI mode switcher:**
- `/settings/performance` или `/settings/profiles`: «Ручная настройка» vs «Автоматическая адаптация»
- Preset «как ручной монтаж» = включает T8.1-T8.5 с дефолтами
- Preset «жёсткий tight» = текущее поведение (обратная совместимость)

**ТРИЗ:**
- «Использовать existing ресурс»: whisper word confidence и punctuation уже считаем — не нужен новый NLP pass.
- «Разделяй и властвуй»: вместо одного глобального threshold — decision tree по контексту.
- «Graceful degrade»: каждый adaptive-компонент имеет fallback на текущее поведение если модель недоступна.

`impact: HIGH (основная жалоба пользователя на «неровность») | effort: 4-6 дней после research | risk: MEDIUM (ML-классификаторы могут false-positive'ить → нужен A/B gate)`

---

## 🎬 T9 — Context-aware composer mode (контроль над cross-scene compilation)

**Проблема пользователя (2026-04-19):** после T2.3 thematic composer pipeline начал склеивать рилсы из разных частей видео — «как телевизионщик: отсюда вырезал, отсюда слепил, получился скандал из контекста». Иногда это работает (виральный микс), иногда превращается в манипуляцию.

**Нужен режим контроля** над тем, когда composer разрешает cross-scene vs требует single-context рилс.

### Research направления (агент изучает)

- Как это обзывается у Opus Clip / Descript / Pictory в UI?
- «Preserve scene context» vs «Allow compilation» — терминология индустрии
- Research по ethics of AI video editing — когда cross-cut становится манипуляцией
- Signals: distance между сегментами в original timeline, тональность (один speaker/speech act?), semantic coherence score

### План (черновик)

**T9.1 — Composer strategy enum в runtime_settings:**
- `composer_strategy`: `tight_context` | `balanced` | `thematic_free`
  - `tight_context` — только соседние сегменты (distance ≤ 60 сек в original), отключает T2.3 thematic clusters
  - `balanced` — разрешает cross-cut в пределах одного chunk (~5 мин), но penalизует дальние прыжки
  - `thematic_free` — текущее поведение после T2.3

**T9.2 — Distance penalty в reels_composer:**
- Добавить `_candidate_context_coherence_score` (currently weight=0) который снижает ranking при большом source-distance
- Веса в balanced mode: если gap > 2 мин → -0.2 к composite_score

**T9.3 — UI в UploadWizard:**
- Дополнительный шаг или collapsed-секция «Стиль монтажа»
- 3 radio buttons с пояснениями на простом языке:
  - «Держаться одного контекста» — безопасно, рилс не «склеивает скандалы»
  - «Немного свободы» — default, разрешает близкие прыжки
  - «Телевизионный микс» — composer свободен компилировать, подходит для ярких нарезок, но требует просмотра
- Tooltip с примером что получится

**T9.4 — UI warning в JobDetail:**
- Если рилс собран из сегментов > 5 мин apart в оригинале — badge «Cross-context» с возможностью preview original timestamps перед публикацией
- Не блокирует, только информирует

**ТРИЗ:**
- «Возможность выбора пользователем» — делаем параметром, не решаем за user'а
- «Прозрачность манипуляции» — badge показывает когда composer сшил из далёких частей, user решает публиковать ли
- «Обратная совместимость» — default = `balanced`, существующие jobs не ломаются

`impact: MEDIUM-HIGH (возвращает контроль user'у) | effort: 1-2 дня | risk: LOW (чистая параметризация + UI)`

---

## 🧬 T6 — Personal ML на лайках (расширение T2.2)

**Текущее состояние:** `services/preference_memory.py` достаёт топ-8 hook-фраз из лайкнутых рилсов и инжектит в Gemini prompt как few-shot anchors. Простой retrieval, без обучения. Cap: 8 хуков × 180 символов = ~600 токенов.

**Research закрыт 2026-04-19** (deep-research-analyst). Сравнивались 5 подходов: cosine retrieval, MLP reward model, SetFit, contrastive embedding fine-tune, DPO/KTO. Вывод ниже.

### Реалистичные зоны по объёму данных

| Объём лайков | Рекомендация |
|---|---|
| **< 30** | Никакой ML не бьёт few-shot промптинг. Текущий подход — оптимален. |
| **30-100** | Cosine retrieval по embeddings (upgrade над топ-8 фраз). MLP если есть negatives. |
| **100-300** | MLP reward model полноценно работает. +10-20% над retrieval. |
| **300+** | Рассмотреть contrastive fine-tune локальных embeddings (E5/BGE). |

**Что НЕ делаем (исключено research'ом):**
- DPO / KTO — не соответствует задаче ranking (они обучают **генерацию**, а нам нужен **scoring**). Архитектурное несоответствие.
- SetFit — 20-50 мс inference vs <1 мс у MLP, при сопоставимом качестве. Избыточен.
- Contrastive fine-tune Gemini embeddings — Gemini embedding API closed, fine-tune невозможен. Перейти на локальный sentence-transformer имеет смысл только от 300+ лайков.
- Collaborative filtering — single-user, нет сигнала от других пользователей.

### План реализации (2 фазы)

**T6.1 — Phase 1: Cosine retrieval upgrade (сейчас, 30-100 лайков)**

Переключить `preference_memory.py` с «топ-8 фраз» на «топ-5 семантически ближайших лайкнутых рилсов к текущему кандидату» через cosine similarity 256-dim Gemini embeddings. У нас embeddings уже есть в инфраструктуре T1.1.

- Хранение: PostgreSQL с `pgvector` extension, `vector(256)` column для каждого лайкнутого рилса.
- Query: `SELECT reel_plan.hook FROM liked_reels ORDER BY embedding <=> :current_embedding LIMIT 5`. Linear scan (<500 records, индекс не нужен).
- Inference overhead: 0 (embeddings уже посчитаны на других стадиях).
- Fallback: если embeddings недоступны (старые job) → оригинальный top-8 по дате.

**T6.2 — Phase 2: MLP reward scorer (при накоплении 80-100+ лайков с negatives)**

sklearn `MLPClassifier(hidden_layer_sizes=(128, 64), alpha=0.01, max_iter=200)` поверх 256-dim embeddings. Бинарная метка: 1=liked, 0=explicit dislike или skipped.

- Training: <30 сек на CPU для 500 примеров. Инкрементальный retrain в background task после каждого нового сигнала (~2-5 сек).
- Inference: <1 мс (forward pass через 2 матрицы). Scoring всех кандидатов перед Gemini prompt.
- Integration: в reducer top-K после LLM rank пересортировывается с учётом preference_score. В composer — candidates получают bonus/penalty.
- Persistence: `joblib.dump/load` sklearn модели (безопасный serialization, не использовать raw pickle). Хранится per-user в `artifacts/user_models/<user_id>/preference_mlp.joblib` (~200 KB).

**T6.3 — UI feedback loop:**
- Кнопка «точно не нравится» на ReelCard (сейчас есть только лайк). Это negative signal для MLP.
- Страница `/settings/my-style` с топ-20 liked embeddings визуализацией (top concepts / themes).
- Индикатор «модель натренирована на N примерах».

### ТРИЗ
- «Использовать existing ресурс»: embeddings уже есть — ML работает поверх них без новых вычислений.
- «Минимальная модель»: single-user не нужна большая сетка — 2-layer MLP достаточно, training на CPU.
- «Graceful degrade»: few-shot остаётся базой; ML добавляется как scorer поверх. Если модель не натренирована (<20 лайков) → используется только retrieval.

### Зависимости
Phase 1: `pgvector` extension в PostgreSQL (если нет — добавить миграцию). Phase 2: `scikit-learn` + `joblib` (уже в стандартном Python data stack).

**Без новых GPU-библиотек. Без fine-tuning. Без новых моделей.**

`impact: MEDIUM-HIGH | effort: T6.1 = 0.5 дня, T6.2 = 2 дня (после накопления данных) | risk: LOW`

---

## ☁️ T7 — Деплой на 2-3 пользователей (облако, не РФ)

**Research закрыт 2026-04-19** (deep-research-analyst). Реальные цены апреля 2026, расчёт на **50 видео/месяц** (10-15/неделю), смешанный хронометраж.

### Профиль нагрузки (baseline)

На A10G (Modal) / A40 (Replicate) / A4000 (RunPod) одно 30-мин видео обрабатывается:
- Whisper large-v3-turbo: **20-35 секунд GPU time** (RTF ~0.005-0.008x на A40)
- Moondream 2 GGUF: работает на CPU (2 GB int4), ~3-5 сек/frame
- Gemini API: облачный, не считается в GPU
- FFmpeg: CPU, пренебрежимо

**Итого GPU time:** ~90 сек/видео (среднее), **~75 минут/месяц** чистого GPU для 50 видео.

### Сравнение сценариев (актуальные цены апрель 2026)

| Сценарий | Базовая $/мес | + 50 видео | Cold start | Сложность | Где хостится |
|---|---|---|---|---|---|
| **A1: Replicate (L40S)** | $0 (backend отдельно) | ~$5-8 GPU | 15-90 сек | Средняя (cog-контейнер) | US |
| **A2: Modal (A10G)** | $0 (free tier $30 credits) | ~$1-3 GPU | 3-15 сек | **Низкая** (FastAPI+GPU в одном app) | US |
| **A3: RunPod Serverless (A4000)** | $0 (backend отдельно) | <$1 GPU | 0.5-2.3 сек (FlashBoot) | Средняя | US/EU |
| **B1: Hetzner GEX44 (RTX 4000 Ada dedicated)** | €184/мес fixed | €184 (GPU простаивает 98%) | 0 (always on) | Высокая (self-managed) | DE |
| **B2: OVH L4 GPU** | hourly $0.91 | ~$45/мес (час billing минимум) | 2-5 мин provisioning | Средняя | FR |
| **B3: Lambda/Paperspace A10** | hourly $0.75 | ~$37/мес | 2-5 мин | Средняя | US |
| **C: Hetzner CX32 + Modal GPU** | €9/мес CPU | +$1-3 GPU | 3-15 сек (только GPU stage) | **Низкая** | DE + US |

### Рекомендация: Сценарий C — Hetzner CX32 + Modal

**Архитектура:**
```
  Browser  →  Hetzner CX32 (DE, €9/мес, always-on)
                │  ├─ Next.js frontend
                │  ├─ FastAPI backend
                │  ├─ PostgreSQL + Redis
                │  ├─ Moondream 2 GGUF (CPU inference ~3-5 sec)
                │  └─ FFmpeg render (CPU)
                │
                ↓ HTTPS .remote() call (только для whisper)
                │
              Modal.com (US, A10G serverless)
                └─ mlx-whisper / faster-whisper endpoint
                   ~90 сек GPU per видео, $0.000306/sec
```

**Почему именно так:**
1. **Modal = единственный provider который хостит FastAPI + GPU workers в одном `modal.App`** (через `@modal.fastapi_endpoint` + `@app.function(gpu="A10G")`). Но у нас уже есть бэкенд на Hetzner — Modal используется только для GPU stage, вызывается из FastAPI через HTTP/gRPC.
2. **Free tier $30/мес credits** покрывает ~50 видео на A10G с огромным запасом.
3. **Cold start 3-15 сек** — допустимо для batch-процесса нарезки видео (не real-time).
4. **Hetzner CX32** — €9/мес, 4 vCPU + 8 GB RAM, Германия. Moondream 2 GGUF (2 GB int4) отлично работает на CPU. Gemini API из EU — без блокировок.

**Почему не:**
- **Replicate:** нет нативного FastAPI хостинга, cog packaging сложнее, cold start дольше, A40 Large исчез из текущего прайса.
- **RunPod Serverless:** дешевле по GPU на ~$0.50/мес, но хуже DX и тоже только inference endpoint.
- **Hetzner GEX44 dedicated GPU (€184/мес):** при 75 мин реального GPU time в месяц — это **$147/час эффективной ставки**. Абсурд для личного использования. Имеет смысл только от 500+ видео/мес.
- **OVH / Lambda / Paperspace:** часовая тарификация → для bursty нагрузки (короткие job) дорого.

### Итоговые расходы для 2-3 пользователей

| Компонент | $/мес |
|---|---|
| Hetzner CX32 (backend + DB + Moondream CPU + FFmpeg) | €9 ≈ $10 |
| Modal A10G GPU (whisper) | $0-3 (free tier) |
| Cloudflare R2 object storage (10 GB артефактов) | $0.15 |
| Gemini API (flash-lite, 50 видео) | $1-5 |
| Домен + SSL (Let's Encrypt) | $1-2 |
| **Итого** | **$12-20/мес** |

### T7.x план реализации

- **T7.1 — Docker + Modal скелет:** `Dockerfile` для backend + frontend, `modal_app.py` с whisper endpoint, локальная проверка через `modal serve`.
- **T7.2 — Hetzner provisioning:** CX32 в Falkenstein, Coolify или ручной docker-compose, Caddy reverse proxy с Let's Encrypt.
- **T7.3 — PostgreSQL + Redis в docker-compose** на том же VPS, с bind mount для persistence.
- **T7.4 — Object Storage (Cloudflare R2):** перенос artifacts с local disk. `artifact_store.py` абстракция уже есть — добавить S3-compatible backend.
- **T7.5 — Multi-user auth:** NextAuth v5 с email-magic-link, 3 пользователя в БД, per-user artifact namespacing `artifacts/<user_id>/<job_id>/`.
- **T7.6 — Secrets через 1Password CLI** (или doppler.com free tier) → .env на production. Gemini API key / Modal token / DB creds.
- **T7.7 — CI/CD GitHub Actions:** push to `main` → build Docker → push to registry → SSH deploy + `docker compose pull && up -d` on Hetzner. Modal deploy через `modal deploy` в отдельном workflow.
- **T7.8 — Monitoring:** Sentry free tier + Modal dashboard + простой `/health` endpoint pinged UptimeRobot (free).

### Ограничения
- **НЕ российский хостинг.** Gemini API блокируется, Moondream weights через HuggingFace тоже.
- Modal US-регион — ok для нашего use-case (не PII-чувствительно, Gemini тоже US).
- Если пользователь из РФ — доступ к фронтенду через VPN/Cloudflare Tunnel.

`impact: HIGH (unblock жены как постоянного пользователя + друга) | effort: 3-5 дней | risk: LOW-MEDIUM (cold start 3-15 сек допустим для batch pipeline)`

---

## 📏 T5 — Infrastructure / измеримость

### T5.1 — Eval dataset (3-5 reference видео)
2.5ч / 1ч / 30мин, 2 fashion + 1 screencast + 1 travel + 1 talking_head. Прогонять после каждой T0/T1 задачи.

`impact: HIGH (без него не видим regression) | effort: 1д | risk: none`

### T5.2 — Baseline metrics snapshot
Зафиксировать сейчас: coherence_score_mean, reel_count_vs_requested, LLM cost, time-to-reel, closure_quality (ручная оценка 1-5). Обновлять после каждой значимой фичи.

`impact: HIGH (база сравнений) | effort: 0.5д | risk: none`

### T5.3 — A/B harness
Возможность параллельно прогнать старый pipeline и новый на одном видео → diff.

`impact: MEDIUM | effort: 2-3д | risk: LOW`

---

## 🧭 Предлагаемая последовательность (моя рекомендация, не план)

**Неделя 1:** T5.1 + T5.2 (eval + baseline) → **T1.1 (semantic embeddings)** → замер эффекта на T0.1 (концовки) + T0.2 (coherence bugs).

**Неделя 2:** T0.3 (next prod mode) за полдня + **T1.2 (cross-visibility Stage 5)** → повторный замер.

**Неделя 3+:** выбор из T2 (hierarchical canvas, rhythm-aware, thematic composer) или T3 (UX handoff) по приоритету пользователя.

**T1.3 (critique loop)** — только если после T1.1+T1.2 концовки всё ещё страдают.

---

## ❌ Что НЕ делаем

- Pro-модель на default — 2.5-flash-lite подтверждено лучше на structured output.
- Fine-tuning моделей — Gemini API не поддерживает для Flash Lite, и для наших объёмов не окупается.
- Unit-тесты на новые фичи (feedback memory) — только ruff/pyright/tsc/pnpm build gates + manual QA на eval-dataset.
- Переписывание работающих частей «красиво». Архитектурные рефакторинги только если снимают конкретную боль.

---

## Решение пользователя (пишу сюда после выбора)

- [ ] Берём T0.1 (концовки, эвристика-only)
- [ ] Берём T0.2 (coherence bugs 4 штуки)
- [ ] Берём T0.3 (next prod mode)
- [ ] Берём T1.1 (semantic embeddings)
- [ ] Берём T1.2 (cross-visibility Stage 5)
- [ ] Берём T1.3 (critique loop)
- [ ] Берём T2.x — укажи номера
- [ ] Берём T3.x — укажи номера
- [ ] Берём T4.x — укажи номера
- [ ] Берём T5.1 + T5.2 (baseline gate)
- [ ] Берём T6.x — preference ML (после research отчёта)
- [ ] Берём T7.x — cloud deploy (после research отчёта)
- [ ] Берём T8.x — adaptive audio editing (ждёт research)
- [ ] Берём T9.x — context-aware composer mode
- [x] **Берём T10.x — editing craft** (механизмы: punchline pause, onset snap, punch-in zoom, variable duration, pacing profiles, match-cut transitions) — ✅ одобрено 2026-04-19
- [x] **Берём T11.x — Automatic Mode** (робот-монтажёр + Manual mode, оба зашиты во фронтенд) — ✅ одобрено 2026-04-19
- [ ] T6.1 cosine retrieval — НЕ сейчас (лайки появятся после достижения качества)
- [ ] T7 cloud deploy — решение отложено
- [ ] T8 adaptive audio cleanup — решение отложено
- [ ] T9 composer mode — решение отложено

### Решение пользователя 2026-04-19 (финальное)

**Принято:** делаем T10 + T11 оба.
**Архитектура:** Manual mode + Automatic mode, оба работают, оба зашиты во frontend.
**GPL-3 зависимости:** одобрено (Parselmouth, pedalboard).
**Ralph Loop:** 6 циклов, completion promise `VIDEOMAKER-T10-T11-AUTOMATIC-MODE-COMPLETE`.

**Распределение 6 циклов:**

| # | Задача | Что внутри |
|---|---|---|
| 1 | **T11.1 Audio Feature Extractor** ✅ (2026-04-19) | `services/audio_analyzer.py` + `models/audio_profile.py`: 6 параллельных extractors через asyncio.to_thread (SNR/loudness/spectral/pitch/VAD-gaps/rhythm-CV). 22 сек на 16-мин видео с 0 failures. _warm_imports() для scipy race condition. Silero-VAD через soundfile+scipy.resample (обход torchcodec dep). |
| 2 | **T10 quick wins** (bundled) ✅ (2026-04-19) | services: `punchline_detector.py` (Parselmouth pitch final lowering), `emphasis_motion.py` (punch-in + Ken Burns planners), расширение `beat_detector.py` (detect_onsets параллельно detect_beats, snap_cuts_to_reference generalized). runtime_settings: punchline_pause_*, snap_strategy enum (beat/onset/both/off), punch_in_zoom_*, ken_burns_drift_*. Все с toggle + intensity. Smoke: 1846 onsets, 247 emphasis peaks, 23 punch-in keyframes на 16-мин видео. |
| 3 | **T11.2 Rule Engine** ✅ (2026-04-19) | `services/auto_config_advisor.py`: advise_config() с 16 решающими правилами (pacing матрица, snap strategy по CV, composer по pitch+kurtosis+wps, punchline hold, punch-in + ken burns, coherence, filler removal). SAFETY_LIMITS circuit breaker. compute_meta_confidence (4 multipliers). generate_warnings (6 user-facing). DecisionEvidence для UI summary. Smoke: typical→balanced/onset/conf 1.0, edge→documentary/off/conf 0.14 + 6 warnings. |
| 4 | **T11.3-T11.5 UI + LLM fallback** ✅ (2026-04-19) | `services/auto_config_llm_fallback.py` (Gemini 2.5 Flash Lite advisor для composer_strategy/coherence/pacing при confidence<0.4, 5сек timeout, graceful-degrade). `POST /jobs/{id}/auto-analyze` endpoint с AutoAnalyzeResponse. Frontend `components/upload/AutoConfigSummary.tsx` — Summary card с метриками, decisions, evidence chain, warnings, кнопки Запустить/Детали/Вручную. `api.ts` типизирован. Build clean (tsc + lint + build). |
| 5 | **T10.4-T10.6 Medium** ✅ (2026-04-19) | `services/pacing_profile.py` — 4 PacingProfileTemplate (dynamic/balanced/mkbhd_clean/documentary) с shot_duration + punch_in + transitions weights + Ken Burns defaults. target_shot_duration_by_energy (energy 0-1 → target sec). `services/transition_chooser.py` — 7 rules (is_last/match_cut/topic_shift/speaker_change/question/energy_peak/period) → hard/j/l/dissolve/dip-to-black/match-cut с правильными durations (0.25-0.50с). Smoke: все 4 profile scale, 6 rules срабатывают на test boundaries. |
| 6 | **T10.8-T10.9 + финал** ✅ (2026-04-19) | `services/eye_trace_continuity.py` — MediaPipe Face Mesh iris (landmarks 468/473) + estimate_gaze_penalty для composer scoring (same-side gaze = BAD, delta > 0.08 = penalty). `services/cross_context_risk.py` — 3 signals (semantic similarity < 0.4 / temporal gap > 5min / sentiment shift > 0.5) → aggregate score 0..1 + human reasons. Smoke: high-risk case score 0.875 с 3 reasons, low-risk 0.0. Все build gates pass: `uv run ruff check src/videomaker` + `pnpm build` 13 routes clean. |

Порядок: _______________________________________
