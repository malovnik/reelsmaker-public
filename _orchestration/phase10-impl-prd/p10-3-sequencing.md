# p10-3 — Sequencing & реализационный план редизайна (вход для Phase 11)

> Роль: Frontend Delivery Lead. Цель: спланировать стройку редизайна по [UI-REDESIGN-SPEC](../phase9-redesign/UI-REDESIGN-SPEC.md) поверх существующих 143 ts/tsx (`apps/frontend/src`), не сломав 89 компонентов на `var(--*)` и не тронув бизнес-логику.
> Опора на факты кода: токены двухслойные (физика `--ink/--paper/--gold` → семантика `--text-primary/--surface-raised/--accent-primary`); 89/118 файлов потребляют преимущественно **семантику**; нет UI-примитивов; роутер eager (705 KB чанк); `router-compat` в 10 файлах; God-компоненты (CampaignDetailClient 878, TinderClient 508, CampaignWizard 491, SubtitleStyleEditor 652, SubtitlePreview 629).

---

## 1. Стратегия миграции токенов: OKLCH → брендбук «латунь на чёрном лаке»

**Решение: замена ЗНАЧЕНИЙ физического слоя + переписывание семантики на брендбук, БЕЗ переименования семантических токенов. Аддитивно по новым токенам.**

Почему так, а не «снести и заново»: семантический слой (`--text-primary`, `--surface-raised`, `--accent-primary`, `--border-default`, `--danger`...) — это **точки потребления в 89 файлах**. Переименовать их = 700+ правок инлайн-классов по всему дереву (overreach, ломает всё). Семантические имена — стабильный интерфейс; меняем то, на что они ссылаются.

### 1.1 Что делаем в `globals.css` (единственный файл правок токенов)

**Слой 1 — физическая палитра (полная замена значений, имена сохраняем где совпадают по роли):**
```
--ink   #0A0A0A (Kuro)      ← было oklch warm-indigo 0.155
--ink-2 #1A1A1A (Sumi/surface)
--ink-3 #202020 (surface-2)
--ink-4 (hover/overlay, дериват #202020 светлее)
--line  #2A2A2A (Hai)       ← было oklch 0.32
--paper #F0E6D2 (Shiroi)    ← было warm-white oklch
--mute / --mute-2 → Kasumi #8A8278 (text-muted) + производная светлее
--gold      #C9A84C (Kinzoku) ← было oklch 0.84 0.16 75
--gold-dim  #B87333 (Dō/copper) или производная Kinzoku
+ НОВЫЕ: --accent-bright #E8C547 (Kogane), --copper #B87333, --danger #8B2500 (Chi)
+ НОВЫЕ деривативы: --accent-soft (gold .10), --accent-line (gold .40),
  --grid-line (.04), --danger-soft (.15)
```

**Слой 2 — семантика (имена те же, перенаправляем на новую физику):**
- `--text-primary → --paper`, `--text-muted → Kasumi`, `--accent-primary → --gold`, `--accent-on-primary` → тёмный Kuro (золото = фон кнопки, текст тёмный), `--danger → Chi`, `--border-default → --line`.
- Профили (`--profile-*`) — оставить как семантические статус-цвета, перекалибровать под палитру (не золото).

**Слой 3 — `@theme` Tailwind 4:** добавить брендовые токены в `@theme`, чтобы появились утилиты (`bg-surface`, `text-accent`). Сейчас `@theme` маппит только шрифты.

### 1.2 Радикальные правила брендбука, требующие правок ВНЕ токенов

Эти три нельзя решить только сменой значений переменных — они меняют визуальную геометрию:

| Правило | Текущее состояние | Действие | Масштаб |
|---|---|---|---|
| `border-radius: 0` глобально | `--radius-s/–/l/xl` = 8–24px; `rounded-*` в 72 файлах; scrollbar radius 12px | Обнулить `--radius-*`=0 в globals + добавить глобальный reset `* { border-radius: 0 }` ИЛИ снять `rounded-*` классы. **Дешёвый путь:** глобальный CSS-override `*{border-radius:0!important}` на время + плановая чистка 72 файлов в пакетах. | 72 файла (чистка), 1 файл (override) |
| `box-shadow` запрещён (глубина слоями) | `--shadow-*` токены + `shadow-*` Tailwind в 15 файлах | Обнулить `--shadow-*`=none, убрать `shadow-*` классы при перевёрстке каждого пакета | 15 файлов |
| Шрифты: Noto Serif JP + Manrope + JetBrains Mono + Press Start 2P | Inter + Geist + JetBrains Mono | Замена `@fontsource` импортов + `--font-*` переменные. Press Start 2P — новый (микро-теги) | 1 файл (globals/fontsource) + точечно классы display |

**Вывод по токенам:** ~95% миграции палитры = правка одного `globals.css` (значения физики + перенаправление семантики). Радиус/тень/шрифты = +глобальные overrides сразу, чистка классов — внутри пакетов перевёрстки. **Ни один семантический токен не переименовывается → 89 файлов на `var(--*)` не ломаются механически, меняется только их вид.**

### 1.3 Риск-чек миграции токенов
- Контраст: Shiroi #F0E6D2 на Kuro #0A0A0A — проверить AA (>4.5). Kasumi #8A8278 на Sumi #1A1A1A — пограничный, проверить на мелком тексте.
- Hardcoded hex в 8 файлах (BrandKitClient, ReelCard viral-градиент, ProjectFormModal/ProjectsList цвет проекта, WaveformBar, FontsRefresh, ProxyCacheManager, JobDetailClient) — это **семантические данные, не chrome**. Viral-градиент (#4ade80→#f87171) и цвет проекта оставить; brand-kit дефолты перекалибровать. Низкий риск.
- `light` тема брендбуком зарезервирована, НЕ переключатель → НЕ строим `[data-theme=light]` (audit предлагал, но spec §1 отменяет). Только dark. Снимает работу.

---

## 2. Последовательность стройки (зависимости)

Жёсткий порядок — каждый слой опора для следующего. Внутри слоя — параллелизм (см. §5).

```
СЛОЙ 0 — Долги-разблокировщики (ДО редизайна, дешёвые кратные выигрыши)
  0a. router lazy() split (FA5-PF1) — eager→lazy все 23 роута. Изолировано в router.tsx.
  0b. Двухуровневый ErrorBoundary (FA4-P0-01/02): root вокруг Outlet + Suspense-fallback с retry.
      → разблокирует безопасный lazy.
        ↓
СЛОЙ 1 — ФУНДАМЕНТ (всё остальное зависит отсюда; делается ПЕРВЫМ и почти последовательно)
  1a. Токены: globals.css миграция (§1) + глобальные overrides radius/shadow + шрифты @fontsource.
  1b. UI-примитивы components/ui/: Button, Card, Input, Select, Switch, Slider,
      Modal, Tooltip, Badge, Field, Skeleton. ОБЯЗАТЕЛЬНЫЙ required `hint`-проп
      на интерактивных (механическая гарантия tooltip для Эксперта, spec §3).
  1c. Контексты+система: UiModeContext (guided|expert, localStorage), тост-система (aria-live),
      humanizeError(), ConfirmDialog + useConfirm (замена 9 confirm в 6 файлах),
      controlHints реестр, lib/nav/routes.ts (единый источник нав).
        ↓ (1b/1c зависят от 1a токенов; 1b — фундамент для всей перевёрстки)
СЛОЙ 2 — ОБОЛОЧКА / НАВ (зависит от примитивов + routes.ts + UiModeContext)
  AppShell, TopBar (sticky 64px, лого Noto Serif JP золото, mono-крошки, сегмент-контрол
  режима справа), NavRail (4 зоны из routes.ts, устранить U-02 дубль), drawer-адаптив,
  SettingsSubNav (единственный источник 8 разделов), Онбординг/welcome (health-gate).
        ↓
СЛОЙ 3 — РЕЖИМЫ (ядро; зависит от оболочки + UiModeContext + Tooltip)
  guided (Пошаговый): мастер S1–S11 поверх UploadWizard/WizardSteps.
  expert (Эксперт-студия): 4-панельный пульт, аккордеон 8 групп, Tooltip на 100% контролов
  (gate-валидатор сборки). Оба режима переиспользуют ОДНИ контролы, меняют раскрытие.
        ↓
СЛОЙ 4 — ЭКРАНЫ (перевёрстка под примитивы; параллелизуемо по доменам, см. §5)
  Dashboard · Job detail (PipelineTimeline SSE + cancel + галерея xl:5/2xl:6 max-w1400) ·
  Clip detail · Tinder · Scheduler/Publer · Projects · Settings (8 страниц).
        ↓
СЛОЙ 5 — ПОЛИРОВКА
  Мемоизация списков (FA5-PF2: ReelCard/JobCard/rows в memo после примитивов) ·
  honesty-бейджи · скелетоны везде · loader-деградация (FA5-P1 toast) ·
  Phase 5/6 visual+engineering validators скилла.
```

**Критические зависимости:** Слой 1b (примитивы) блокирует Слои 2–4 — нельзя верстать экраны до примитивов, иначе двойная работа. Слой 1a (токены) блокирует всё визуальное. routes.ts/UiModeContext (1c) блокируют оболочку (2) и режимы (3).

---

## 3. Переиспользуемость: as-is / переверстать / снести

**Переиспользовать БЕЗ изменений (переживает редизайн):**
- Весь `lib/` (api, api/*, sse, viralScore, video-thumbnail, constants) и `hooks/useSettingsSave`.
- Все `loader()` в `pages/*` и `useWizardState` — data-логика.
- `settings-shared/` (Group/NumberRow/SliderRow/SelectRow/SwitchRow) и `performance-groups/` (28 групп), `post-production/` — это де-факто зародыш UI-примитивов с уже обязательным `hint`. **Переиспользовать как основу для components/ui/, не строить с нуля.**
- Доменная типизация.

**Переверстать (логику сохранить, сменить chrome на примитивы+токены):**
- Все `*Client.tsx`, тонкие `pages/*`, shell (AppShell/NavRail/TopBar), все карточки/списки (ReelCard, ReelGrid, JobCard, JobList, ScheduleTimeline), модалки, визард.
- Снять `rounded-*` (72 файла), `shadow-*` (15 файлов) — в рамках перевёрстки своего пакета.

**Снести / рефакторить:**
- 9× `window.confirm`/`confirm` (6 файлов) → ConfirmDialog/useConfirm.
- Сырые ошибки (JSON.stringify в 6+ местах) → humanizeError.
- `api.ts` дубль-фасад, no-op `resolveUrl`, инлайн `fetch` в WaveformBar — низкий приоритет, по ходу.
- Мёртвый YouTube-OAuth, `chaptered` UI (скрыть в guided), декоративные/dormant фикции → honesty-бейджи (spec §7).
- Дублирование нав (U-02): NavRail top-level settings → одна точка через routes.ts/SettingsSubNav.

---

## 4. Риски

| Риск | Где | Митигация |
|---|---|---|
| **God-компоненты** | CampaignDetailClient 878 (17 useState, 9 className-блоков под confirm), SubtitleStyleEditor 652, SubtitlePreview 629, TinderClient 508, CampaignWizard 491 | Декомпозировать ПЕРЕД перевёрсткой по образцу `performance-groups/` (под-секции + кастом-хук стейта). Разбивка = одна задача внутри своего пакета, не отдельный слой. Изолировать в один пакет (Scheduler), чтобы декомпозиция не пересекалась с другими агентами. |
| **router-compat наследие** | 10 файлов используют `useRouter().push()` / usePathname / notFound поверх react-router | НЕ мигрировать в редизайне (overreach, риск). Зафиксировать как осознанный compat. routes.ts строить рядом, не ломая compat. Точечная миграция — отдельный пост-долг. |
| **Отсутствие примитивов = множитель стоимости** | весь `components/` | Слой 1b строго до Слоёв 2–4. Запрет начинать перевёрстку экрана до готовности примитивов (gate). |
| **Конфликты агентов на globals.css** | 1 файл, нужен всем | globals.css правит ТОЛЬКО Пакет A (фундамент) и замораживается до старта Слоёв 2–4. Остальные агенты globals.css не трогают. |
| **tooltip-gate в Эксперте** | spec требует 100% контролов с подсказкой | Механически через required `hint`-проп примитивов (1b) + controlHints реестр + gate-валидатор в build. Нельзя собрать контрол без hint. |
| **Молчаливая деградация loaders** | `.catch(()=>null)` во всех pages | Слой 5, не блокер. toast при сетевой ошибке. |
| **Контраст Kasumi на Sumi** | мелкий текст | Проверить в Phase 5 visual validator (скриншоты). |

---

## 5. Разбивка на ~5 непересекающихся пакетов для Phase 11

Принцип нарезки: **по доменам файлов** так, чтобы агенты не редактировали одни и те же файлы. Слой 0+1 (Пакет A) — последовательная преамбула, исполняется ОДНИМ агентом и блокирует остальных. Пакеты B–E параллельны после A.

### Пакет A — ФУНДАМЕНТ + долги (СНАЧАЛА, блокирует B–E)
**Один агент, последовательно. Завершить и заморозить globals.css/ui/ до старта B–E.**
Файлы: `globals.css`, `router.tsx`, новые `components/ui/*`, `components/shell/*` (AppShell/NavRail/TopBar), `lib/nav/routes.ts`, новые `lib/UiModeContext`, `lib/humanizeError`, `lib/toast`, `components/ui/ConfirmDialog`+`useConfirm`, ErrorBoundary, `@fontsource` импорты.
Содержит: Слой 0 (lazy split + ErrorBoundary), Слой 1 (токены+примитивы+контексты+система), Слой 2 (оболочка/нав/онбординг).
Выход-контракт для B–E: стабильные имена примитивов, props `hint`, токены, `routes.ts`, `useUiMode()`, `useToast()`, `useConfirm()`.

### Пакет B — Студия: режимы + загрузка/визард (guided+expert ядро)
Файлы: `components/upload/*` (UploadWizard, WizardSteps, useWizardState, AspectPreview, AutoConfigSummary, VideoPreviewCard), новый guided-мастер S1–S11, новый expert 4-панельный пульт + аккордеон 8 групп, `pages/HomePage` + `components/HomeClient`, `controlHints` реестр.
Зависит от A. Не пересекается с C/D/E.

### Пакет C — Job/Reel домен (просмотр результатов)
Файлы: `components/job/*` (ВСЕ 12: JobHero, PipelineTimeline, ReelCard, ReelGrid, HeatmapBar, TinderClient, ClipDetailClient, CaptionsEditor, ClipScrubber, ExportDialog, ArtifactsAccordion, WaveformBar), `components/JobDetailClient`, `components/JobList`, `components/dashboard/*` (JobCard, DashboardHero, BulkActions, FilterChipRow, ResultsFilters), `pages/{JobDetailPage,ClipDetailPage,JobTinderPage,HomePage-loader}`.
Включает: галерея xl:5/2xl:6 max-w1400 (VD-02), tach-видимые действия (VD-03), Tinder 3 кнопки+клавиши, мемоизация ReelCard/JobCard (после примитивов A).
Зависит от A. **Декомпозиция TinderClient 508** живёт здесь.

### Пакет D — Scheduler/Publer + Projects (God-компоненты изолированы)
Файлы: `components/scheduler/*` (ВСЕ 10, вкл. CampaignDetailClient 878, CampaignWizard 491, ScheduleTimeline 417), `components/projects/*`, `pages/{SchedulerPage,AccountsPage,NewCampaignPage,PresetsPage,CampaignDetailPage,ProjectsPage,ProjectFolderPage}`, `lib/constants/scheduler`.
Включает: **декомпозиция CampaignDetailClient + CampaignWizard** (самые тяжёлые God-компоненты — в одном пакете, чтобы не пересекаться), 4-шаг мастер кампании, honesty-статусы публикаций (409/502), замена 5 confirm здесь.
Зависит от A. Самый тяжёлый пакет по LOC — возможно дать 1.5 агента или больше времени.

### Пакет E — Settings домен (8 разделов)
Файлы: `components/settings/*` (BrandKitClient, SettingsSubNav, performance-groups/* 29, post-production/* 10), `components/settings-shared/*`, `components/{PerformanceSettingsClient,PostProductionSettingsClient,SubtitleSettingsClient,SubtitleStyleEditor,SubtitlePreview,PromptsEditorClient,VisionProfilesSettingsClient,MoondreamSettings,ProfileSelector,SplitScreenPreviewEditor,TranscriptCacheBadge}`, `components/maintenance/*`, `pages/{SettingsLayout,BrandKitPage,ModelsPage,PerformanceSettingsPage,PostProductionSettingsPage,VisionProfilesPage,PromptsPage,SubtitleSettingsPage,MaintenancePage}`.
Включает: единая sub-nav (U-02), Tooltip на всех контролах, **декомпозиция SubtitleStyleEditor 652 + SubtitlePreview 629**, замена confirm здесь. `settings-shared/` → выровнять под новые `components/ui/` примитивы (или оставить как доменную надстройку над ними).
Зависит от A.

**Карта непересечения (файловые домены):**
- A: globals.css, router.tsx, components/ui/*, components/shell/*, lib/nav, lib системные.
- B: components/upload/*, HomeClient, guided/expert новые.
- C: components/job/*, components/dashboard/*, JobDetailClient, JobList.
- D: components/scheduler/*, components/projects/*.
- E: components/settings*, settings-shared, maintenance, остальные settings-Client'ы.
- pages/* делятся по домену (job-pages→C, scheduler/projects-pages→D, settings-pages→E, home→B). Единственная общая точка — `router.tsx` (правит только A в Слое 0).

---

## 6. Build-gates (на каждом пакете)

После каждого пакета, перед мержем:
```
pnpm --filter frontend build      # Vite prod build проходит
pnpm --filter frontend exec tsc --noEmit   # 0 type errors
```
(точные команды сверить с `apps/frontend/package.json` scripts; типобезопасность сильная — tsc обязателен).

Дополнительно по spec:
- **Gate tooltip-валидатор** (после B/E): ни один контрол Эксперта без `hint` (механически через required props + проверка controlHints покрытия).
- **Финал** (после E5/полировки): Phase 3 engineering validator (spacing/perf — отдельный чистый агент) + Phase 5 visual validator (скриншоты desktop 1280 + mobile 375, проверка radius=0, нет box-shadow, золото ≤25-30%, контраст) + Phase 6 pre-commit checklist.
- Запрет на регресс: не ломать существующие loaders/api (data-слой заморожен).

---

## Резюме для Phase 11
1. **Токены:** замена значений физического слоя + перенаправление семантики на брендбук в одном `globals.css`; семантические имена НЕ переименовываем → 89 файлов не ломаются. radius=0 и no-box-shadow — глобальные overrides сразу + чистка классов в пакетах. Light-тема НЕ строим (spec резервирует).
2. **Порядок:** долги(lazy+ErrorBoundary) → фундамент(токены+примитивы+контексты+система) → оболочка/нав → режимы → экраны → полировка. Примитивы строго до перевёрстки.
3. **5 пакетов:** A фундамент (последовательный, блокирующий) → параллельно B Студия/визард, C Job/Reel, D Scheduler/Projects (тяжёлые God-компоненты изолированы), E Settings. Нарезка по файловым доменам, единственная общая точка router.tsx правится только A.
