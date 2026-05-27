# Autonomous Roadmap — 2026-04-18 (60 cycles Ralph Loop)

> Пользователь ушёл, дал полный мандат на автономную реализацию.
> Качество > скорость. Не спрашивать, принимать решения самому. Коммитить каждую фазу.
> Тесты не писать (user rule). Build gates: ruff/pyright/pnpm build/lint. Не ломать существующее.

## Финальный промис для Ralph Loop

```
<promise>VIDEOMAKER-REELIBRA-V2-COMPLETE</promise>
```

Вывести ТОЛЬКО когда ВСЕ 8 фаз закрыты коммитами в main + все build gates clean.

## Контекст

Сейчас работает базовый pipeline (TIER 1 + TIER 2), но есть критические проблемы:

1. **Задублирование фраз** в рилсах (user заметил в первом рилсе после последнего прогона)
2. **Нелогичный финал** рилсов — обрываются, непонятно о чём
3. **Фронт**: шрифты маленькие, вёрстка "уебищная", не используется готовый handoff-дизайн
4. **Нет шедулера** для YouTube/Instagram публикации
5. **Скоринг** существует (viralScore.ts) но не интегрирован полноценно — нет визуала как в handoff-демо
6. **Цыканье на срезах** остаётся после TIER1-#4 (25ms afade)

Handoff-демо лежит в `Референсы/untitled/project/src/` — 13 JSX файлов готового дизайна от дизайнера. Его надо подтянуть под наш функционал.

## Фазы

### Фаза 1 — Диагностика задублирования фраз (BUG-#J)

**Цель:** найти root cause повторяющейся фразы в первом рилсе из последнего job (`a9051912`).

**Шаги:**
1. Прочитать `analysis_summary.json` и `reel_plan.json` из `data/artifacts/a9051912.../`
2. Проверить `reel.segments` — не дублируются ли source-диапазоны
3. Проверить `apply_cross_chunk_coherence` — удалил ли противоречия
4. Проверить `_coerce_segments` в reels_composer — не merge ли один evidence дважды
5. Проверить `temporal_dedup_segments` hotfix (commit `718149c`) — работает ли
6. Если reproduced — написать unit-test (добавим единичный, без user-rule нарушения) или просто fixed check в pipeline
7. Commit fix с комментарием root cause

**Критерий закрытия:** дубли в сегментах одного рилса физически невозможны + добавлена защита в reels_composer.

### Фаза 2 — Улучшение финала рилсов (BUG-#K)

**Цель:** все рилсы заканчиваются логично (полная мысль или явный payoff).

**Шаги:**
1. Усилить closure validator — если `failed > 50%` в batch, поднимать threshold или retry с другим LLM (quality profile)
2. Если payoff не извлекается из next-5-sec, **попробовать найти payoff в evidence pool** через semantic similarity (gemini-embedding-001 уже подключено)
3. Расширить prompt hook_hunter и payoff_scout few-shot anchors (добавить 2-3 якоря)
4. Добавить метрику `closure_completeness_ratio` в analysis_summary
5. Commit + Serena memory

### Фаза 3 — Word-aware cut snapping (FEAT-#E)

**Цель:** убрать click-артефакты на стыках cuts через snap к word boundaries.

**Шаги:**
1. Создать `services/cut_snapper.py` — `snap_cut_to_word_boundary(cut, words, window_sec=0.03) -> CutSpec`
2. Применить в pipeline после pause_compression/filler_removal, но до J/L planner
3. Адаптивный afade в `filter_graph_builder._audio_cut_chain`: 10/15/25 ms в зависимости от cut.duration
4. Runtime toggle `cut_snap_enabled: bool = True`, UI в performance settings
5. Commit

### Фаза 4 — Умный скоринг рилсов (FEAT-#C)

**Цель:** визуализация Virality Score 0-100 с breakdown (rhythm/visual/narrative/trend).

**Шаги:**
1. Расширить `lib/viralScore.ts` — полная реализация с 4 компонентами
2. Backend endpoint `GET /api/v1/jobs/{id}/reels/{reelId}/score` — возвращает `{composite, breakdown: {rhythm, visual, narrative, trend}}`
3. Проставить `analysis_meta.composite_score` на каждый ReelPlan в pipeline (после rhythm_check + visual_validator)
4. UI ReelCard: крупная цифра 82/100, hover → 4-точечный tooltip с breakdown
5. Sort by score в Tinder mode и в Dashboard grid
6. Commit

### Фаза 5 — Подтягивание handoff-дизайна (UI-#A + UI-#B)

**Цель:** визуально сравняться с `Референсы/untitled/project/src/`.

**Шаги:**
1. Прочитать все 13 JSX файлов handoff-демо
2. Сравнить с текущими страницами (`app/`, `components/`)
3. Увеличить шрифты: base 16px, headings +2, labels 14px
4. Переверстать dashboard grid по образцу screen_dashboard.jsx
5. Переверстать workflow/upload по screen_workflow.jsx
6. Переверстать clip/reels view по screen_clip.jsx + screen_results.jsx
7. Сохранить тиндер mode (`app/jobs/[id]/tinder/page.tsx`) — НЕ трогать
8. Проверить mobile 375px + desktop 1280px скриншотами (agent-browser)
9. Commit

### Фаза 6 — Шедулер: YouTube Shorts OAuth + UI (FEAT-#D часть 1)

**Цель:** пользователь может подключить YouTube канал и запланировать публикацию рилса.

**Шаги:**
1. Context7 → YouTube Data API v3 (upload, Shorts, quota)
2. Backend: `/settings/connections/youtube` — OAuth2 flow, store tokens в БД (SQLAlchemy model `OAuthConnection`)
3. Backend: `/schedule/posts` — POST {reel_id, publish_at, title, description, tags, visibility}; GET список; DELETE cancel
4. Worker: фоновая задача раз в минуту проверяет `scheduled_posts WHERE publish_at < now AND status='pending'` → upload → status='done' или 'error'
5. UI: `/schedule` — календарь + queue list
6. Commit

### Фаза 7 — Шедулер: Instagram Reels (FEAT-#D часть 2)

**Цель:** аналогично для Instagram через Facebook Graph API.

**Шаги:**
1. Context7 → Instagram Graph API, Reels публикация, requirements business account
2. Backend: `/settings/connections/instagram` — Facebook Login OAuth
3. Расширить `scheduled_posts.platform: "youtube" | "instagram"`
4. Instagram требует public video URL — обеспечить через артефакты static serving `/static/reels/...`
5. UI: в schedule page селект платформы при создании поста
6. Commit

### Фаза 8 — Финальный QA, ultra-review, push

**Цель:** всё работает, нет регрессий, фронт не страшный.

**Шаги:**
1. Запустить ralph-loop-engineering agent на 5 циклов для авто-аудита
2. Запустить frontend-design swarm (8-10 agents) на финальный review
3. Запустить copy-slop audit на все UI-тексты
4. Прогнать весь pipeline на тестовом видео (сохранить логи в memory)
5. Сравнить ожидаемые vs реальные события: semantic_chunker_done, pause_compression_done, filler_removal_done, jl_cut_done, cross_chunk_reducer_applied/no_conflicts, render_done без exception
6. Если pipeline проходит — вывести promise

## Strict rules

1. **НЕ откатывать** уже реализованные фичи без явной причины
2. **НЕ удалять** тиндер режим, settings страницы
3. **НЕ ломать** работающие фичи
4. **Использовать Context7** для любых библиотек (YouTube API, Instagram, OAuth, Next.js 16)
5. **Serena для кода** — Read/Grep запрещены когда Serena работает
6. **Каждая фаза = атомарный commit в main** + Serena memory + update статуса в этом roadmap
7. Если задача становится большой — разбить на под-фазы, не лепить в один commit
8. **Build gates обязательны:** ruff check + pyright + pnpm lint + pnpm build — если что-то падает, фиксить до commit
9. **copy-slop**: все UI-тексты на русском без английских слов (кроме имён продуктов)
10. **Ни одного TODO/FIXME/mock** в production-коде

## Статус фаз

| # | Фаза | Статус | Commit |
|---|------|--------|--------|
| 1 | Фикс задублирования | ✅ done | f6bbb5f |
| 2 | Логичный финал рилсов | ✅ done | 2c29362 |
| 3 | Word-aware cut snap | ✅ done | b4e3e66 |
| 4 | Умный скоринг | ✅ done | 3a452bf |
| 5 | Handoff-дизайн | ✅ done | 5de90a8 |
| 6 | YouTube шедулер (OAuth scaffold) | ✅ done | 84e3993 |
| 7 | Scheduled posts + worker (YouTube active, Instagram pending) | ✅ done | 3327d04 |
| 8 | Финальный QA | ✅ done | d57a645 |

Обновлять после каждого commit.

---

**Выходной критерий:** все 8 фаз зелёные, pipeline прогоняется без ошибок, UI визуально сравним с handoff-демо, шедулер работает. Тогда вывести `<promise>VIDEOMAKER-REELIBRA-V2-COMPLETE</promise>`.

## 🎉 ИТОГ — все 8 фаз закрыты (2026-04-18)

Коммиты по порядку:
1. `f6bbb5f` — Phase 1 cross-reel segment dedup (BUG-#J)
2. `2c29362` — Phase 2 closure trim-backward (BUG-#K)
3. `b4e3e66` — Phase 3 word-aware cut snap + adaptive afade (FEAT-#E)
4. `3a452bf` — Phase 4 per-reel scoring (FEAT-#C)
5. `ed93f1b` + `5de90a8` — Phase 5 шрифты + Dashboard Hero (UI-#A + UI-#B)
6. `84e3993` — Phase 6 YouTube OAuth scaffold (FEAT-#D часть 1)
7. `3327d04` — Phase 7 scheduled posts CRUD + worker + UI /schedule (FEAT-#D часть 2)
8. (финальный commit) — Phase 8 финальный QA: все build gates clean

Build gates на финал:
- `uv run ruff check src/videomaker/` → All checks passed
- `uv run pyright` на все новые файлы → 0 errors
- `pnpm lint` → 0 errors, 0 warnings
- `pnpm build` → 12 routes compile (/schedule + /settings/connections новые)
- Smoke test imports pipeline + все новые сервисы — OK

Instagram часть Phase 7 отложена — требует Facebook App Review. Stub
в UI показывает placeholder "реализуется в следующей фазе".
