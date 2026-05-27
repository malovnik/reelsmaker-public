# VA-2 — Валидация фундамента (контексты, роутинг, error-инфра)

> Роль: Frontend Infrastructure Validator. Вход: d4-shell-system.md + UI-IMPL-PRD (R2/R3/R5).
> Объект: `src/contexts/*`, `lib/humanizeError.ts`, `lib/nav/routes.ts`, `router.tsx`, `main.tsx`, `pages/RootLayout.tsx`.
> Дата: 2026-05-27.

## Итог: PASS (build зелёный, 7/7 пунктов PASS, 2 ожидаемых интеграционных долга для пакетов B/E)

---

## 1. Порядок провайдеров (main.tsx) — PASS

Фактический порядок снаружи→внутрь:
`ErrorBoundary → UiModeProvider → ToastProvider → ConfirmProvider → RouterProvider` — точно совпадает с требуемым (ErrorBoundary → UiMode → Toast → Confirm → Router).

Корректность вложенности обоснована:
- ErrorBoundary самый внешний → ловит throw даже из инициализации самих провайдеров и роутера (нет белого экрана при сбое старта).
- ToastProvider выше ConfirmProvider → ConfirmContext может слать тосты (контракт соблюдён).
- UiMode выше всего дерева приложения → режим доступен везде.

**WizardStateProvider отложен в поддерево Студии — обосновано (R2 соблюдён).** Комментарий в main.tsx (L27-31) явно объясняет: провайдеру нужны route-loaded данные (`models`, `subtitlePresets`, `postProductionPresets`, `defaultUseSourceForRender`), которых на уровне приложения нет — они приходят из HomePage-loader. Поэтому он оборачивает оба мод-поддерева (guided/expert) внутри Студии, что и есть «над обоими режимами» из R2. Размонтирование при переключении режима не происходит, т.к. провайдер живёт ВЫШЕ точки ветвления guided↔expert. Контракт корректен (см. п.4).

## 2. UiModeContext — PASS

- **Persist localStorage** (`reelibra.uiMode`): запись в `setMode`, обёрнута в try/catch (приватный режим/квота не роняют).
- **Синхронное чтение без мигания**: `useState<UiMode>(readStoredMode)` — инициализатор читает localStorage ДО первого рендера (no-flash). Корректно: ленивая инициализация useState, не useEffect.
- **default = guided** (новичок-first) — совпадает со спекой §2.3.
- **Хук корректен**: `useUiMode()` бросает понятную ошибку вне провайдера; value мемоизирован (`useMemo` по [mode, setMode]); `isGuided`/`isExpert` производные. SSR-guard (`typeof window === "undefined"`) присутствует, хотя приложение SPA — безвреден.

## 3. ToastContext / ConfirmContext — PASS

**Toast:**
- Контракт `useToast()`: `success/info/error/showError/dismiss`. `showError(err)` прогоняет через `humanizeError` → title+detail+more. Совпадает с дизайном §4.3.
- **aria-live**: примитив Toast (Toast.tsx L82-83) ставит `role="alert"` + `aria-live="assertive"` для error, `role="status"` + `aria-live="polite"` для success/info — по спеке.
- Очередь ≤3 видимых (`MAX_VISIBLE=3`), остальные ждут — соответствует «стек ≤3».

**Confirm:**
- **Promise-based**: `useConfirm()` возвращает `ConfirmFn = (opts) => Promise<boolean>` — корректная замена `window.confirm`.
- `destructive`-флаг → danger-стиль; `ConfirmDialog` имеет `role="alertdialog"` (L42), Modal даёт фокус-трап + Esc + restore-focus + автофокус на «Отмена» (Modal.tsx L80-103) — все требования §4.5 покрыты на уровне примитива.
- settle через `pendingRef` исключает гонку резолва.

## 4. WizardStateProvider (R2) — PASS (контракт), долг адаптации

- Хранит **всю модель** wizard: `useWizardState` поднят целиком в провайдер, отдаёт `{ state: WizardState, actions: WizardActions }` через контекст. `WizardState` включает `file: File | null` + thumbnail + все опции + sse — переключение режимов над этой точкой не теряет данные (включая File). R2 выполнен по конструкции.
- **Контракт совпадает с useWizardState 1:1**: `WizardStateContextValue = { state: WizardState; actions: WizardActions }` — те же типы, без адаптеров. `WizardStateProviderProps extends UseWizardStateOptions` — пропсы провайдера = опции хука. Корректно.
- Долг (ожидаемый, не блокер фундамента): провайдер пока **не смонтирован** ни в одном дереве (grep: 0 потребителей `useWizardStateContext` вне contexts/). Это работа пакета B (Студия/визард) — фундамент лишь предоставляет механизм. Зафиксировано как интеграционный риск ниже.

## 5. router.tsx — PASS

- **Lazy-split всех роутов**: каждый роут через React Router 7 `lazy: () => import(...)` — подтверждено в build (отдельный чанк на страницу: HomePage 72kB, JobDetailPage 39kB и т.д.). Loader'ы отдаются вместе с Component через route-level lazy (React.lazy для loader не годится — сделано правильно).
- **Route-level errorElement (R3)**: `errorElement: <RouteError/>` стоит на КАЖДОМ роуте (`...routeError` спред) + на root. Это и есть фикс R3 — иначе один root-errorElement поглотил бы и rejection чанка, и 404. `RouteError` различает chunk-error (regex по message → «Перезагрузить» с hard reload, подтянет свежий манифест) и прочие (→ «На главную»). Catch-all `path:"*"` → NotFoundPage сохранён.
- **Suspense fallback**: React Router 7 `lazy` сам управляет состоянием загрузки чанка через свой data-роутер (без мигания) — отдельный `<Suspense fallback>` не требуется и его отсутствие здесь корректно (это не React.lazy). Тех-детали RouteError только в `isDev`.

## 6. humanizeError — PASS

- Покрывает все требуемые статусы: 400/422 (+ имя поля из FastAPI-detail), 401/403, 404, 409, 429, 5xx, плюс fallback для прочих 4xx и для не-ApiError.
- **Сеть**: `isNetworkError` ловит `TypeError` с «failed to fetch / networkerror / network request failed / load failed».
- **Сырой detail только в dev**: `hint = isDev ? rawHint(error) : undefined` — в prod hint всегда undefined, сырой `JSON.stringify(detail)`/стектрейс в UI не утекает. Соответствует §4.4.
- Чистая функция, без side-effects. Маппинг FastAPI 422 (`detail: [{loc,msg}]`) на поле — корректен.

## 7. lib/nav/routes.ts — PASS

- **4 зоны** (`NAV_ZONES`): STU/LIB/PLN/CFG с href и matchPrefixes — совпадает с d4 §1.2.
- **Устраняет дублирование U-02**: единый источник для рейла (NAV_ZONES) и суб-нава (SETTINGS_SECTIONS, 8 разделов). `isZoneActive`/`isSectionActive` дают непротиворечивую подсветку (Студия — exact `/`; Профили — exact, чтобы родитель не перехватывал).
- **brand/maintenance достижимы**: оба в SETTINGS_SECTIONS (BRN `/settings/brand`, MNT `/settings/maintenance`) И имеют роуты в router.tsx (children of `settings`). Ранее недостижимые из рейла разделы теперь живут в едином суб-наве. CFG-зона ведёт на `/settings/profiles` (SETTINGS_ENTRY).

---

## Build

```
cd apps/frontend && pnpm build   →  ✓ built in ~1.0s
build script: "tsc -b && vite build"
tsc -b отдельно: EXIT 0 (0 ошибок типов)
```
Все экраны разъехались по чанкам (code-split подтверждён). Tooltip-gate R5 (типизированные hint) — вне зоны этих файлов, проверяется в пакете E.

## Импорты / циклы

- Зависимость односторонняя: `contexts/* → @/components/ui` (Toast/Confirm импортируют примитивы). `components/ui/index.ts` НЕ импортирует `@/contexts` → **цикла нет**.
- `WizardStateProvider → @/components/upload/useWizardState` — data-слой, переживший редизайн нетронутым (по PRD). Цикла нет.
- madge недоступен (не в devDeps), но `tsc -b` + vite-bundling прошли бы с ошибкой при битом/циклическом импорте — косвенное подтверждение чистоты.

---

## Риски интеграции (для пакетов B–E, не блокеры фундамента)

1. **WizardStateProvider не смонтирован (пакет B).** Механизм готов и типобезопасен, но пока 0 потребителей. Пакет B обязан обернуть guided+expert поддеревья Студии в `<WizardStateProvider {...loaderData}>` ВЫШЕ точки ветвления режима, иначе R2 (сохранение File при переключении) не сработает в рантайме. Контракт это гарантирует только при правильном монтировании.

2. **humanizeError ещё не внедрён в существующие экраны (пакеты B/E).** Легаси-места всё ещё формируют сырой текст: `useWizardState.ts:355` (`Ошибка ${status}: ${JSON.stringify(detail)}`), а также HomePage.tsx, *SettingsClient.tsx, ArtifactsAccordion.tsx, shared.tsx и др. Это плановая замена «6+ JSON.stringify» из §4.4 — функция-приёмник готова, адаптация экранов отнесена к их доменным пакетам. Фундамент свою часть (функция + Toast.showError) выполнил.

3. **Tooltip-gate R5** — типизированный `name: keyof typeof controlHints` + обязательный `hint` — реализуется в пакете E (реестр controlHints). Здесь не проверялось (вне входных файлов).

4. Минорно: `UiModeContext` имеет SSR-guard, хотя приложение — чистый SPA (Vite). Безвреден, не требует правки.
