# FRONTEND-EXPOSURE — что бэкенда выведено во фронтенд (текущее состояние)

> Консолидация Phase 3 (3 агента). Второй ключевой документ. Вход для Phase 4 (gap-анализ → PRD).
> Разделы: [A — API-клиент](exposure-A-api-client.md) · [B — UI-поверхность](exposure-B-ui-surface.md) · [C — Потоки](exposure-C-user-flows.md)

## Сводка покрытия
- **API-клиент: 74/81 эндпоинта покрыто.** Орфанов клиента нет (мёртвого клиентского кода нет).
- **Стек фронта:** React 19 + Vite + Tailwind 4 + react-router 7. 22 страницы → 18 роутов, 9 в NavRail. Fetch-слой `core.ts` (relative URL, `ApiError`, 204→undefined); SSE отдельно через native `EventSource`.

## Не покрыто клиентом (7 эндпоинтов)
1. `GET /files/{job_id}/{kind}/{name}` (download, вероятно инлайн в JSX)
2-4. **Весь proxies-роутер** (`GET /proxies`, `DELETE /proxies/cleanup`, `DELETE /proxies/{sha256}`) — нет UI кэша прокси
5. `GET /post_production/assets/{id}/thumbnail`
6. `GET /jobs/{job_id}/source-thumbnail`
7. **`PATCH`+`DELETE /jobs/{job_id}/auto-config`** — самый материальный пробел: половина Automatic-Mode флоу без клиента

## Класс «выведено СЛОМАННЫМ» (приоритет для PRD)
| Проблема | Суть | Где |
|----------|------|-----|
| 🔴 `/settings/connections` — мёртвый UI | зовёт удалённые `/connections/youtube/*` (роутер+таблица дропнуты Publer-миграцией) → кнопка всегда падает | ConnectionsSettings |
| 🔴 Export-диалог врёт | показывает TikTok/Reels/Shorts/X битрейт+LUFS пресеты, но бэк не перекодирует (отдаёт исходник) | job/ExportDialog |
| 🔴 LLM tier/quality тоггл врёт | fast/legacy + lite → всё резолвится в Flash-Lite, «pro» не запускается | settings/performance, ModelsPage |
| 🔴 `chaptered` режим | выбираемый radio, помечен автором broken | UploadWizard |
| 🔴 Provider-селекты | листают мёртвые anthropic/openai/deepgram как pipeline-LLM | UploadWizard, ModelsPage |
| 🔴 Assignment cancel | флипает локальный статус, не отзывает Publer-пост | scheduler |

## Обрывы пользовательского потока (8)
1. **Проекты ↔ джобы оторваны** — `project_id` не шлётся, `assignJobToProject` не вызывается. Папки нерабочие e2e.
2. Экспорт — заглушка (см. выше).
3. **`ManualPublishButton` — мёртвый компонент** (реализован, не отрендерен).
4. Viral-score считается на клиенте (`viralScore.ts`), не из пайплайна.
5. **Два механизма публикации** — Publer-кампании (`/scheduler/*`) vs legacy `/schedule`. Не пересекаются, путают.
6. После `done` на главной — только мелкая ссылка «Открыть детали».
7. **Нет кнопки отмены джоба** (хотя бэк + SSE поддерживают — а после 1b-fix cancel реально работает!).
8. «Сохранить в папку» — нет экрана папки, файлы не найти.

## Возможности бэка без UI-контрола (топ)
profile/suggestion, mouth_sound_removal, screencast/deictic zoom (поля есть, UI скрыт), proxies-purge, fonts/refresh, cancel job, specific llm_model.

## Контраст экспозиции
- `/settings/performance` (~25 групп) **переэкспонирует** dormant-фичи: multi-arc, cross-chunk, ensemble, semantic chunking, J/L cuts, face-tracker, vision — рабочие тоглы при OFF-дефолте.
- Скрытые (mouth-sound, screencast/deictic zoom) намеренно подавлены, чтобы не давать ложный контроль.

## Контракт-расхождения
- `updateArtifactLike`: клиент шлёт tri-state `none|like|dislike`, контракт описывает boolean `liked` — риск 422, проверить Pydantic-модель.

## Вердикт про онбординг/пошаговость
**Онбординга нет** (только инлайн-подсказка про `GEMINI_API_KEY`). Главный поток (UploadWizard) — псевдо-пошаговый (нумерация, но один скролл-экран; auto-режим реально ведёт новичка). Единственный настоящий мастер — `CampaignWizard` (4 шага). Остальное — разрозненные экраны. **Это прямо обосновывает Phase 9: режим «Пошаговый» нужен, его сейчас по сути нет.**
