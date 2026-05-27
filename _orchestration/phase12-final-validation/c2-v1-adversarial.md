# C2-V1 Adversarial Runtime Breaker — цикл 2/3

Роль: Adversarial Runtime Breaker. Цель — найти, чем фронтенд падает в рантайме.
Дата: 2026-05-27. Скоуп: `apps/frontend/src`.

## Итог одной строкой

Уронить в белый экран не удалось. Архитектура устойчивости зрелая: loader'ы с per-call `.catch()` фолбэками, многослойные error boundaries, humanizeError на всех путях ошибок, lossless-переключение режимов визарда, защищённые empty/error tristate. Найдено 3 минорных косметических риска (стейл-данные, NaN-дата), 0 краш-рисков уровня CRITICAL/HIGH.

## Build / Preview

- `pnpm build` (tsc -b && vite build) — **exit 0**, `✓ built in ~1s`. TS-ошибок нет. Чанки кодсплита на месте (HomePage 92KB, index 327KB и т.д.).
- `pnpm preview --port 4319` — **HTTP 200** на `/`.
  - `<div id="root">` присутствует, не пустой бэйл (пустой root для CSR-SPA — норма, React гидрирует в рантайме).
  - module-script `/assets/index-Bh8_IzOE.js` → HTTP 200.
  - SPA-фолбэк на несуществующий deep-route `/jobs/abc/tinder` → HTTP 200 (отдаёт index.html, роутер разрулит). Белого экрана от прямого захода на вложенный путь нет.
- `timeout` в окружении отсутствует (zsh) — preview гасился через `lsof -ti :PORT | xargs kill`. Заглушен.

## По пунктам задачи

### 1. Edge-кейсы данных — ЗАЩИЩЕНО
- **Пустые массивы:** `JobList` (нет джобов → empty-state «Пока ни одной нарезки»; пустая категория после фильтра → отдельный empty-state). `ProjectsList` (нет проектов → CTA «Создать первый»). `JobDetailClient` (нет рилсов → status-aware сообщение: error/done-без-артефактов/в процессе).
- **null-поля:** `avg_composite_score`, `source_duration_sec` — сортировки используют `?? -1 / ?? 0`. `project.color`/`description` — `|| FALLBACK` / `|| "Без описания"`. `display_name ?? source_filename`. `job.progress`/`message`/`current_stage` — `?? job.* ?? default`.
- **Отсутствующие thumbnails:** `extractVideoThumbnail` ловит всё в try/catch, резолвит `null`, ревокает Object URL в finally; `vw===0||vh===0` и `getContext===null` → ранний `null`. UI рисует плейсхолдер-текст «Выбери видео…».
- **Job без артефактов:** `reels = artifacts.filter(kind==="reel_output")`; `reels.length===0` ветка покрыта.

### 2. Пути ошибок — ЗАЩИЩЕНО
- **humanizeError** маппит 400/422/401/403/404/409/429/5xx + сетевую (`TypeError: failed to fetch` и пр.) + FastAPI-422 `detail[]`. Сырой технический хинт только в `import.meta.env.DEV`. Тосты и инлайн-ошибки форм используют его. Белого экрана от 500/422/сети нет — пользователь видит человеческий русский текст.
- **Loader HomePage:** все 7 API-вызовов индивидуально обёрнуты `.catch(() => null/[])`. При недоступном бэке `data.models===null` → дружелюбный экран «Сервер не отвечает, запусти ./run.sh», а не throw.
- **SSE (`useJobSse`):** экспоненциальный реконнект `[1,2,4,8,15]с`, после исчерпания — текст «перезагрузи страницу» (не краш). При финальном статусе реконнект не запускается (`finalRef`). `JSON.parse` обёрнут try/catch → ошибка в `setError`, не throw. Cleanup закрывает source и таймер.

### 3. Переключение guided↔expert посередине заполнения — ЗАЩИЩЕНО (явно спроектировано)
`WizardStateProvider` смонтирован НАД обоими режимами в `HomeClient`; `useWizardState` вызывается один раз выше дерева режимов. Переключение `useUiMode` (persist в localStorage, синхронное чтение — no-flash) меняет только отображаемое поддерево, store не размонтируется. File, project_id, все опции, sourceThumbnailDataUrl сохраняются. localStorage обёрнут try/catch (приватный режим/квота → дефолт guided, без падения).

### 4. Пошаговая машина / навигация / отмена — ЗАЩИЩЕНО
- **CampaignWizard:** `WizardStepper` кликабелен только для пройденных шагов (`clickable = done`); будущие — `disabled`. Прыжка вперёд в обход валидации нет. `handleNext` гейтится `canAdvance`, `step<4`; cast `(prev+1) as WizardStep` безопасен из-за гейтов (не переполнит 4). Back-nav сохраняет state (живёт на уровне визарда).
- **Повторный сабмит:** двойная защита — `canSubmit && !pendingRef.current`; `submitting` дизейблит кнопку. При ошибке создания — rollback (`deleteCampaign`). Expert-форма: submit дизейблится при `uploading || autoAnalyzing || !!autoAnalysis`.
- **Отмена джоба в стадиях:** `JobDetailClient.handleCancel` — confirm-диалог, обновляет статус из ответа, ошибку в тост; `cancelling` блокирует повтор. `useWizardState.cancel` — гард `!jobId`, ошибка через humanizeError.

### 5. Build + Preview — см. секцию выше (всё зелёное).

### 6. Error boundaries — ЗАЩИЩЕНО (4 слоя)
- **main.tsx:** root `<ErrorBoundary>` вокруг провайдеров — последний рубеж.
- **RootLayout.tsx:** `<ErrorBoundary>` вокруг `<Outlet/>` — рантайм-throw компонента ловится здесь, НЕ уносит весь SPA (есть reset + «На главную»).
- **router.tsx:** `errorElement: <RouteError/>` на КАЖДОМ роуте — ловит throw из loader'ов и rejection lazy-чанков; детектит chunk-load-error (`/loading dynamically imported module/i`) → предлагает hard-reload (новый деплой). Не существующий путь → 404 (catch-all).
- Тех-детали в boundaries — только в DEV.

Вывод по п.6: throw в одном экране НЕ роняет весь SPA — изолируется ближайшим boundary вокруг Outlet, остальная оболочка (NavRail/TopBar) живёт.

## Найденные риски

| # | Severity | Где | Что | Падает? |
|---|----------|-----|-----|---------|
| R1 | LOW (cosmetic) | `JobList.tsx` | Держит локальный `useState(initial)` от пропа `jobs`, но `HomeClient` поллит и передаёт свежие джобы. Нет `useEffect` синка проп→стейт → список не обновляется на фоновом polling'е (только локальные rename/delete видны). | Не падает. Стейл-отображение. Дублированный стейт (HomeClient тоже держит jobs) — рассинхрон. |
| R2 | LOW (cosmetic) | `JobCard.tsx` `formatRelative` | Битый/отсутствующий `created_at` → `Date.now()-NaN` → «NaN мин назад» / «Invalid Date» в `toLocaleDateString`. Date не бросает на плохом вводе. | Не падает. Косметика. (В отличие от scheduler/ProjectsList, тут нет try/catch вокруг даты.) |
| R3 | LOW | `useWizardState.submit` | `narrative_mode` патчится в ГЛОБАЛЬНЫЕ performance-настройки до создания джоба (read-modify-write без блокировки). Параллельные сабмиты двух вкладок могут перетереть режим друг друга. Best-effort, обёрнут try/catch. | Не падает. Возможен гонками неверный narrative_mode у джоба. |

Ничего из найденного не приводит к белому экрану, throw или потере данных пользователя.

## Что РЕАЛЬНО падает vs ЗАЩИЩЕНО

- **Реально падает:** ничего из проверенного (build clean, preview 200, все edge-пути имеют фолбэк/boundary).
- **Защищено:** пустые/null/error данные, сетевые и HTTP-ошибки, обрыв SSE, переключение режимов с файлом, back-nav и повторный сабмит, отмена джоба, throw в компоненте (изолируется boundary).
- **Косметические недочёты:** R1 (стейл JobList), R2 (NaN-дата в JobCard), R3 (гонка narrative_mode).

## Рекомендации (опционально, не блокеры)
- R1: либо поднять источник истины джобов в один компонент (HomeClient владеет → JobList stateless по списку), либо добавить синк `useEffect(() => setJobs(initial), [initial])` в JobList.
- R2: обернуть `formatRelative` в проверку `Number.isNaN(date.getTime())` → фолбэк на «—», как сделано в scheduler/ProjectsList.
