# GAP-ANALYSIS — что упущено / выведено сломанным

> Консолидация Phase 4 (3 сварм-агента, 3 линзы: coverage / broken-flows / capability-alignment). Дедуп, единые ID, приоритеты.
> Линзы: [gap-1 coverage](gap-1-coverage.md) · [gap-2 broken+flows](gap-2-broken-flows.md) · [gap-3 capability](gap-3-capability-alignment.md)
> Вход для PRD-expose.md. Привязка к продуктовым решениям (PD1-PD4) из ROADMAP.

## Сводка по приоритетам
| Приоритет | Кол-во | Суть |
|-----------|--------|------|
| P0 | 9 | падает / активно врёт / рвёт главный поток |
| P1 | 11 | заметный обрыв или ложь, не блокирует ядро |
| P2 | 3 | косметика/мелочь |
| WONTFIX-by-decision | 9+ | dormant/orphan/auth — не трогаем по решению |

---

## A. GAP-BROKEN — выведено, но врёт/не работает (чиним по-настоящему, PD1)
| ID | Приоритет | Слож. | Что врёт сейчас | Целевое поведение |
|----|-----------|-------|-----------------|-------------------|
| BR-01 | P0 | M | `/settings/connections` YouTube OAuth — роутер+таблица дропнуты Publer-миграцией, кнопка всегда падает | Удалить мёртвый UI; публикация только через Publer (PD3) |
| BR-02 | P0 | L | export-stub — пресеты битрейт/LUFS косметика, бэк не перекодирует, отдаёт исходник | Реальный ffmpeg-transcode через существующий render-путь (PD1) |
| BR-03 | P0 | M | LLM-tier фикция — «pro»/«flash» всегда = Flash-Lite | **Вариант A**: развести на реальные модели в tier_resolver, рабочий тоггл, дефолт Flash-Lite (PD1+PD4) |
| BR-04 | P1 | S | `chaptered`-режим broken, но выбираем radio | Убрать из UI (нет рабочего call-site) |
| BR-05 | P1 | S | provider-селекты листают мёртвые anthropic/openai/deepgram как pipeline-LLM | Убрать мёртвые опции, оставить реальные (gemini/zhipu) |
| BR-06 | P0 | M | assignment cancel — флипает локальный статус, пост уходит в соцсети | Реальный retract через Publer DELETE (PD3) |
| BR-07 | P1 | S | `updateArtifactLike` tri-state vs boolean `liked` → 422-риск, рвёт вход в публикацию (ReelPicker берёт лайкнутые) | Согласовать контракт клиент↔Pydantic |

## B. GAP-FLOWBREAK — обрыв сценария (PD3)
| ID | Приоритет | Слож. | Обрыв | Целевое |
|----|-----------|-------|-------|---------|
| FL-01 | P0 | M | проекты↔джобы оторваны (`project_id` не шлётся, `assignJobToProject` мёртв) | Слать project_id из визарда + вызвать assign; папки рабочие e2e |
| FL-02 | P0 | M | два механизма публикации (legacy `/schedule` vs Publer) | Удалить legacy `/schedule`+`ScheduleButton`; Publer единый (PD3) |
| FL-03 | P1 | S | `ManualPublishButton` — мёртвый компонент (реализован, не отрендерен) | Подключить → `manual/publish-one` как «быстрая публикация» |
| FL-04 | P1 | S | нет cancel-кнопки джоба (хотя бэк после 1b-fix реально умеет) | Кнопка отмены → `POST /jobs/{id}/cancel` |
| FL-05 | P2 | S | viral-score считается на клиенте, выдаётся за «оценку движка» | Честная подпись или из пайплайна |
| FL-06 | P1 | S | после `done` на главной — только мелкая ссылка | Явный CTA к результату |
| FL-07 | P1 | M | нет экрана папки `saved/<folder>` | Экран папки/просмотр сохранённых |

## C. GAP-NOTEXPOSED — бэк есть, UI/клиента нет (PD1/PD2)
| ID | Приоритет | Слож. | Эндпоинт | Действие |
|----|-----------|-------|----------|----------|
| NX-01/02 | P0 | M | `PATCH`+`DELETE /jobs/{id}/auto-config` — нет клиента (Automatic Mode полу-сломан) | Добавить клиент + UI apply/clear |
| NX-03 | P1 | S | `GET /jobs/{id}/profile/suggestion` — клиент есть, UI-триггера нет | Вывести триггер (PD2) |
| NX-04/05/06 | P2 | S | весь proxies-роутер (list/cleanup/delete) | UI управления кэшем прокси (или Эксперт-режим) |
| NX-07 | P2 | S | `POST /settings/fonts/refresh` — клиент есть, кнопки нет | Кнопка refresh |
| NX-08/09 | P2 | S | source-thumbnail, assets/thumbnail — нет URL-хелперов | URL-хелперы |

## D. GAP-MISSING — возможность pipeline без UI
| ID | Приоритет | Слож. | Возможность | Действие |
|----|-----------|-------|-------------|----------|
| MS-01 | P0 | S | cancel running job (бэк+SSE готовы) | = FL-04 |
| MS-02 | P1 | M | выбор реальной модели / tier | = BR-03 |
| MS-03 | P0 | M | projects↔jobs + saved-folder | = FL-01/FL-07 |

## E. Vision/face-tracking opt-in revival (PD2, единственная настоящая инженерная работа)
| ID | Слож. | Что нужно |
|----|-------|-----------|
| VS-01 | M | hard-таймаут вокруг mediapipe-детекта + фолбэк на center-crop (причина OFF = hang на Apple Silicon) |
| VS-02 | S | честный двухуровневый тоггл: `vision.enabled` + `face_tracker_enabled`, дефолт безопасный |
| VS-03 | S | UI-контрол с пометкой «экспериментально/opt-in» |
Эндпоинты уже есть (`/settings/vision`, `/settings/profiles/*`, `profile/suggestion`). Dormant/orphan НЕ трогаем.

## F. Два режима (фундамент для Phase 9)
- **Пошаговый**: линейная цепочка на ~8 ручек (create project → POST /jobs с project_id → profile/suggestion → auto-analyze/auto-config → SSE+cancel → разметка like → publish → папка). Сейчас настоящего wizard НЕТ (псевдо-пошаговый скролл) — L-фича Phase 9.
- **Эксперт-студия**: ~81 ручка почти выведена (`/settings/*`, scheduler, proxies). Задача не добавить, а очистить от фикций + tooltip на 100% контролов.
- **Онбординг**: отсутствует. Нужен welcome + `GET /health`-проверка + переключатель режимов в shell (P0 для Phase 9).

## WONTFIX-by-decision
- Auth на открытых деструктивных эндпоинтах — локальный single-user (PD-auth).
- Dormant: mouth_sound_removal, screencast cursor zoom, deictic zoom (PD4 — режем/прячем, не оживляем).
- Orphan ~972 LOC (B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser) — удалить, не выводить (нет эндпоинтов).
- B-roll как продукт, persistent job queue — вне скоупа «честного рабочего сервиса».
