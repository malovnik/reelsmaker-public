# ReelsMaker — Master Roadmap (автономная доводка до рабочего сервиса)

> Источник: `malovnik/videomaker-old @ feat/vite-migration`. Репо: `malovnik/reelsmaker-public` (private → public после security-скана).
> Это durable state. Любой агент/сессия читает отсюда статус. Обновлять после каждой фазы + commit/push.

## Принципы исполнения
- Все агенты снаряжаются: профессиональная роль + soul-элементы + Chain of Thought (крупные шаги → 5-7 подшагов → 3-7 подподшагов).
- LLM-рантайм сервиса = только Gemini (стек проекта). Это не про агентов-разработчиков.
- Промежуточные коммиты+пуши обязательны после каждой фазы.
- NO MOCKS/STUBS/TODO в финальном коде. Production-ready.
- Не трогаем исходные репо videomaker / videomaker-old.

## Фазы

| # | Фаза | Агентов | Артефакт | Статус |
|---|------|---------|----------|--------|
| 0 | Создание repo + среда | — | repo + _orchestration/ | ✅ DONE |
| 1 | Аудит всех функций и ручек бэкенда | 5 swarm | agent-reports/ | ✅ DONE |
| 1b | Что реально подключено vs заглушки | 5 swarm | STUB-REALITY-MAP.md | ✅ DONE |
| 1b-fix | Оркестрация доводки заглушек | 3 | safe fixes landed | ✅ DONE (safe set) |
| 2 | Консолидация → 3 агента пишут карту софта | 3 | BACKEND-MAP.md | ✅ DONE |
| 3 | Что сейчас выведено во фронтенд | 3 | FRONTEND-EXPOSURE.md | ✅ DONE |
| 4 | Gap: что упущено/не выведено наружу | 3 | GAP + PRD-expose.md | ⬜ |
| 5 | Валидация PRD | — | — | ⬜ |
| 6 | Доработка вывода бэка во фронт | N | код | ⬜ |
| 7 | 3 валидатора → консолидация → фикс дыр | 3 | — | ⬜ |
| 8 | Аудит фронта: usability/design/стабильность | 5 swarm | FRONTEND-AUDIT.md | ⬜ |
| 9 | Редизайн (frontend-design skill активирован) + брендбук → 2 режима (Пошаговый / Эксперт-студия) | 5 swarm | UI-REDESIGN-SPEC.md | ⬜ |
| 10 | 3 агента (frontend skill): PRD vs бэкенд-ручки vs логика UI | 3 | UI-IMPL-PRD.md | ⬜ |
| 11 | Оркестрация исполнения → рабочая система | N | код | ⬜ |
| 12 | Валидация ×3 цикла (3 агента каждый: прогон→отчёт→правки) | 3×3 | — | ⬜ |
| 13 | Security-скан секретов → private→public | — | — | ⬜ |

## Брендбук
`/Users/malovnik/Documents/malovnik-obsidian/😎 Бизнес/БрендБук` (Phase 9).

## Два режима интерфейса (цель Phase 9)
1. **Пошаговый**: логическая цепочка от «Создай проект» (крупная кнопка) до получения видео — выбор вида рилсов, шаблонов/субтитров, обработки, локальных/облачных моделей.
2. **Эксперт-студия**: много настроек + подсказка напротив 100% ручек/кнопок/ползунков/галочек.

## Бэкенд (факты разведки)
- 184 py, ~47K LOC. Роуты: health, files, jobs(52KB), post_production, projects, proxies, scheduler(32KB), settings.
- services/: 11 поддоменов (narrative, vision, video_effects, broll, transcribers, llm_clients, llm_providers, pipeline_stages, publer, agents) + ~85 top-level сервисов.
- core: artifacts, config, db, logging. models: 18 файлов.

## Лог фаз
- Phase 0 (DONE): clean copy через git archive (582 файла, без секретов/данных/истории), private repo, main branch, orchestration scaffold.
