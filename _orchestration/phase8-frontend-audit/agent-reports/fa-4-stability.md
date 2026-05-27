# FA-4 — Аудит стабильности и устойчивости к падениям (Frontend)

Роль: Frontend Reliability Engineer. Стек: React 19, react-router 7 (`createBrowserRouter`), нативный EventSource.
Скоуп: `apps/frontend/src`.

## Резюме

Кодовая база в целом дисциплинированная: loader'ы оборачивают fetch в `.catch`, числовые `toFixed` защищены проверками `typeof === "number"`, `JSON.parse` из localStorage — в try/catch, polling-эффекты чистятся и привязаны к булевым флагам (нет утечек таймеров). Главный системный пробел — **полное отсутствие React Error Boundary**: единственная защита это `errorElement` в react-router, который НЕ ловит ошибки рендера в дочерних компонентах после успешной загрузки loader'а. Любой неперехваченный throw в фазе рендера = белый экран всего приложения.

---

## P0 — Белый экран

### FA4-P0-01 — Нет ни одного React Error Boundary; render-time throw кладёт всё приложение
Файлы: `main.tsx:20-24`, `router.tsx:44-47`
Поиск по `ErrorBoundary|componentDidCatch|getDerivedStateFromError` — 0 совпадений. В дереве только `<StrictMode><RouterProvider/></StrictMode>`.
`errorElement: <NotFoundPage />` стоит лишь на root-route и в react-router ловит ошибки **loader/action и рендера элемента маршрута**, но если исключение бросается внутри клиентского компонента уже ПОСЛЕ монтирования (например в обработчике рендера при обновлении состояния от SSE/polling, или при доступе к неожиданной форме `meta`), react-router его не перехватывает в той же мере — а для не-route ошибок React 19 по умолчанию размонтирует всё дерево → белый экран.
Фикс: добавить классовый `ErrorBoundary` (`getDerivedStateFromError` + `componentDidCatch`) и обернуть `<Outlet/>` в `RootLayout.tsx`, чтобы крах одной страницы давал fallback внутри AppShell, а не пустой `<body>`. Дополнительно — `errorElement` на каждой route-ветке (сейчас наследуется только корневой).

### FA4-P0-02 — Lazy-роут `ProjectFolderPage` без error-обработки чанка
Файл: `router.tsx:15`, `53-59`
`const ProjectFolderPage = lazy(() => import(...))` обёрнут в `<Suspense fallback>`, но НЕ в errorElement/boundary. Если динамический чанк не загрузится (протухший деплой, обрыв сети, кэш) — promise reject из `lazy` всплывает как render-error и роняет дерево белым экраном; Suspense ловит только pending, не rejection.
Фикс: дать этой route-ветке свой `errorElement` либо обернуть в ErrorBoundary с кнопкой «перезагрузить».

---

## P1 — Деградация, частичные сбои, утечки

### FA4-P1-01 — SSE: возможная утечка EventSource при гонке reconnect
Файл: `lib/sse.ts:67-122`
В `connect()` новый `EventSource` сразу пишется в `sourceRef.current = source`. При reconnect по таймеру (`setTimeout(connect, delay)`) старый source уже закрыт в `onerror` (`source.close()`), это ок. Но если `jobId` меняется во время ожидающего reconnect-таймера, cleanup (стр. 127-136) закрывает `sourceRef.current` (текущий) и чистит таймер — корректно. Реальный риск тоньше: `onmessage` при финальном статусе делает `source.close()` но НЕ чистит `reconnectTimerRef` — если перед этим `onerror` успел запланировать reconnect, таймер выстрелит, создаст новый EventSource к уже завершённому job'у, и `sourceRef` перезапишется без гарантии закрытия предыдущего. Низкая вероятность, но это лишнее соединение + лишний стейт.
Фикс: в ветке финального статуса (`onmessage`, стр. 88-92) очищать `reconnectTimerRef` перед `source.close()`.

### FA4-P1-02 — SSE `onmessage` парсит без проверки структуры; «миссы» молча копятся
Файл: `lib/sse.ts:79-97`
`JSON.parse(event.data)` обёрнут в try/catch (хорошо), но при парс-ошибке только пишется `setError`, событие теряется, а соединение продолжает слать события — UI застрянет с последним валидным `lastEvent`, при этом баннер ошибки противоречит «connected: true». Не падение, но рассинхрон состояния. Низкий приоритет.

### FA4-P1-03 — Race: устаревший ответ refetch в JobDetailClient
Файл: `components/JobDetailClient.tsx:42-57`
Эффект на `sse.finalStatus` делает `Promise.all([getJob, listArtifacts])` без отмены/guard'а. Если пользователь быстро уходит/возвращается или job меняется, поздний ответ может записать stale-данные. `job.id` стабилен в рамках страницы, поэтому риск низкий, но cancellation-флаг (как в `ProjectFolderPage` и `CampaignDetailClient`) здесь отсутствует. Ошибки проглочены (`catch {}`) — это осознанно.
Фикс: добавить `let cancelled` guard как в остальных компонентах.

### FA4-P1-04 — Двойной сабмит формы загрузки защищён только через `disabled`, не через ref-guard
Файл: `components/upload/useWizardState.ts:264-266`, `UploadWizard.tsx:783-792`
`submit()` начинается с `if (!file) return`, затем `setUploading(true)`. Кнопка `disabled` при `uploading`. Это закрывает обычный кейс. Но `setUploading` асинхронен — при очень быстром двойном клике (или вызове из кода) два `submit` могут пройти проверку до ре-рендера. На обычном UI риск низкий (клик блокируется браузером по disabled), но строго это не идемпотентно. Сабмит по Enter в форме не используется (кнопка `type="button"`), так что основной вектор закрыт.
Фикс (опционально): ранний `if (uploading) return` через `useRef`-guard, не зависящий от ре-рендера.

---

## P2 — Замечания (не валят UI)

- `components/job/TinderClient.tsx:39-41,182` — индексация `reels[index]` и guard `if (!current) return null` корректны; пустой/завершённый список обработан через `EmptyShell`. `meta as Record` (стр. 185) с безопасным доступом через `typeof`. Чисто.
- `lib/viralScore.ts` — полностью defensive (`asNumber`, `clamp01`, NaN-guard). Краша не даёт даже на мусорном meta.
- Числовые `.toFixed` по всему коду (`ReelCard`, `ClipDetailClient`, `JobCard`, `AutoConfigSummary`) — везде за проверкой `typeof === "number"` либо над заведомо числовым полем. Безопасно.
- `ScheduleTimeline.tsx:64`, `CampaignDetailClient.tsx:736` — `split(":")`/`split("/")[1]` с `?? "0"` и optional chaining. Безопасно.
- Polling: `HomeClient.tsx:47-54` (флаг `hasActiveJobs`, не массив — нет лавины таймеров) и `CampaignDetailClient.tsx:435-456` (cancelled-guard + clearInterval + visibility-gate) — образцово.
- Loaders (`HomePage`, `SchedulerPage`, `JobDetailPage`, `CampaignDetailPage`, `ClipDetailPage`) — все оборачивают сетевые вызовы в `.catch`/try либо явно `notFound()`. HomePage даже рендерит дружелюбный fallback при `!models`.

---

## Состояние Error Boundaries

Отсутствуют как класс. Есть только react-router `errorElement` (`NotFoundPage`) на корневом маршруте — он закрывает ошибки loader'ов и 404, но НЕ render-time throw в живых компонентах и НЕ rejection lazy-чанка. Это единственная критическая дыра устойчивости. Рекомендация: классовый ErrorBoundary вокруг `<Outlet/>` в `RootLayout` + per-route `errorElement`.

## Надёжность SSE

Хорошая база: экспоненциальный backoff `[1,2,4,8,15]с`, `onopen` сбрасывает счётчик, финальный статус останавливает reconnect, cleanup закрывает source и таймер при unmount/смене jobId. Дыры: (1) reconnect-таймер не чистится в ветке финального статуса `onmessage` → редкий лишний EventSource (FA4-P1-01); (2) при исчерпании попыток показывается терминальная ошибка с просьбой перезагрузить — приемлемо. Утечек при штатном unmount нет.

## Топ-приоритеты к фиксу
1. FA4-P0-01 — ErrorBoundary вокруг Outlet (главный риск белого экрана).
2. FA4-P0-02 — обработка ошибки загрузки lazy-чанка ProjectFolderPage.
3. FA4-P1-01 — чистка reconnect-таймера в финальном SSE-событии.
