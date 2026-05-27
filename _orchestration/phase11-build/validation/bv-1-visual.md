# BV-1 — Visual Consistency Validation (Phase 11)

Роль: Visual Consistency Validator. Источники: брендбук 02-color-palette / 10-website-style + UI-REDESIGN-SPEC. Код: `apps/frontend/src` (Vite SPA, не Next.js).

## Главный контекст (важно для трактовки)
`src/globals.css` использует **двухслойную систему токенов** (строки 19-21):
- Физика: `--ink / --paper / --gold / --line / --mute / --ember`.
- **Старые семантические токены (`--surface-raised`, `--accent-primary`, `--border-default`, `--text-primary` и т.д.) НЕ переименованы — они алиасятся на новую палитру** ("89 файлов НЕ переименована").

Следствие: файл, использующий старый словарь токенов, **всё равно рендерит правильные цвета бренда**. Старый словарь != старый вид. Поэтому критерий «старый стиль» здесь — не имя токена, а **рендерящаяся off-brand геометрия/цвет**: pill-скругления (`rounded-full`, `rounded-[..]`), реальные хардкод-цвета вне токенов, неоновые градиенты.

Также globals.css обнуляет все Tailwind `--radius-*` → `0` и все `--shadow-{xs..lg}` → `none`. Значит:
- `rounded-sm/md/lg/xl/2xl` → **no-op** (рендерятся прямыми углами). Косметический долг словаря, не визуальный баг.
- `shadow-[var(--shadow-*)]`, `shadow-lg/md/sm/xs/inner` → **no-op** (теней нет). Не нарушение.
- `rounded-full` и `rounded-[Npx]` → **рендерятся** (НЕ обнулены) → реальные нарушения «прямые углы».

---

## 1. Компоненты «на старом словаре токенов» (косметический долг, цвета верны)

Файлы используют только старый словарь токенов (`--surface-raised`/`--accent-primary`/`--border-default`/`--text-primary`), но рендерятся в правильной палитре через алиасы. Перевёрстка желательна для единообразия кода, **но это не визуальный регресс**:

Чистый старый словарь (21 файл):
- Top-level settings-клиенты: `SubtitleStyleEditor.tsx`, `SubtitleSettingsClient.tsx`, `VisionProfilesSettingsClient.tsx`, `PromptsEditorClient.tsx`, `MoondreamSettings.tsx`, `PostProductionSettingsClient.tsx`, `SubtitlePreview.tsx`, `TranscriptCacheBadge.tsx`, `ProfileSelector.tsx`
- dashboard: `BulkActions.tsx`, `FilterChipRow.tsx`, `JobCard.tsx`, `ResultsFilters.tsx`
- job: `ArtifactsAccordion.tsx`, `ClipScrubber.tsx`, `JobHero.tsx`, `PipelineTimeline.tsx`, `ReelGrid.tsx`, `WaveformBar.tsx`
- upload: `AspectPreview.tsx`, `VideoPreviewCard.tsx`

Уточнение по спеке: `PerformanceSettingsClient.tsx` — тонкая обёртка без собственных токенов/скруглений; реальный UI делегирован в `settings/performance-groups/*`, **все они на новом словаре**. Не считается старым. `ModelsClient/AccountsClient/PromptsClient` в указанном виде не существуют (есть `PromptsEditorClient` + страницы `*Page` + scheduler `AccountProfilesDashboard`).

Смешанный словарь (частичная миграция, 12 файлов): `HomeClient`, `JobDetailClient`, `JobList`, `job/ReelCard`, `upload/UploadWizard`, `upload/WizardSteps`, и scheduler `AccountProfilesDashboard / AccountsPicker / CaptionPresetsDashboard / ManualPublishButton / ReelPicker / ScheduleTimeline`.

---

## 2. Реальные визуальные нарушения (рендерятся off-brand) — ПРИОРИТЕТ

### CRITICAL — неоновый градиент (прямой запрет брендбука)
- `SubtitlePreview.tsx:356` — `bg-gradient-to-br from-violet-700 via-purple-600 to-fuchsia-600`. Фиолетово-фуксиевый градиент = «кислотный/неоновый» + «градиент» — оба в списке запрещённых сочетаний (02-color-palette). Должен быть нейтральный тёмный фон-холст (`--ink`/`--ink-3`) под превью субтитра. Самое грубое нарушение в кодовой базе.

### MEDIUM — pill-скругления (нарушают «прямые углы», реально рендерятся)
`rounded-full` рендерится (не обнулён). Всего **70 вхождений** вне `ui/`. Заметные в перевёрстываемых зонах:
- `TranscriptCacheBadge.tsx` (27, 32, 47, 75, 80) — бейджи-пилюли.
- `VisionProfilesSettingsClient.tsx` (215, 476, 478), `SubtitleSettingsClient.tsx` (270, 275), `MoondreamSettings.tsx` (82) — пилюли-теги и прогресс-бары.
- `JobList.tsx` (158, 258, 274, 292, 310), `ProfileSelector.tsx` (122, 130, 186, 188), `dashboard/JobCard.tsx` (128, 141, 143, 206, 215, 231) — кнопки/индикаторы-капсулы.
- `job/TinderClient.tsx` (266, 282) поверх видео.

Примечание: круглые **статус-дотты** (`size-1.5 rounded-full`, `size-2 rounded-full`) и прогресс-бары — точечно допустимы как функциональные индикаторы; пилюли-кнопки/бейджи-теги — нет (бренд требует прямых тегов `card-tag`).

### LOW — `rounded-[Npx]` / `rounded-xl` arbitrary (рендерятся)
- `ProfileSelector.tsx:93,169` — `rounded-xl` на карточках/тултипе (карточка должна быть `border-radius:0`).
- `job/ClipScrubber.tsx:60` — `rounded-xl bg-black` (видео-холст, скругление лишнее).

### Хардкод-цвета — разбор по контексту
Легитимные (НЕ нарушения):
- `SplitScreenPreviewEditor.tsx:102,296` (`#fff`/`#000`), `SubtitlePreview.tsx` `bg-black` letterbox, `job/ReelCard.tsx` / `job/ClipScrubber` / `TinderClient` `bg-black` + `text-white/xx` — это **чрома видеоплеера поверх реального видео 9:16**; чёрный letterbox и белый оверлей-текст по UX оправданы.
- `BrandKitClient.tsx:13-15` (`#b79b5b` и т.д.) — **значения данных** фичи «бренд-кит» (дефолты пользовательских цветов), не UI-стайлинг.
- `ProjectFormModal.tsx:13` `#C9A84C` — дефолтный цвет проекта (Kinzoku, в палитре).
- `job/WaveformBar.tsx:55` `#78716c`, `job/ReelCard.tsx:458-466` (шкала скора зелёный→красный) — canvas/score-heatmap значения; приемлемо, но скор-шкала использует generic tailwind-хексы (`#4ade80…#f87171`) — желательно вынести в danger/gold токены (минор).

Реальный минор-хардкод:
- `ManualEditingPresetCard.tsx:24` — `bg-violet-600 ... hover:bg-violet-700 text-white`. Фиолетовая кнопка = вне палитры. Должна быть `--gold` / `.btn`. (Файл при этом на новом словаре — единичный промах.)
- `ProfileSelector.tsx:130` — `text-white` на цветном кружке (минор).

---

## 3. Брендбук-консистентность (вердикт)

| Критерий | Статус | Замечание |
|---|---|---|
| Тёмная база #0A0A0A, без light mode | PASS | `--ink` канва, light зарезервирован |
| Текст #F0E6D2 (не чистый белый) | PASS* | `--paper`; `text-white` только в видео-оверлеях/1 промах |
| Прямые углы (border-radius:0) | PARTIAL | radius-токены обнулены, но 70× `rounded-full` + неск. `rounded-xl/[px]` рендерятся как пилюли |
| Золото ≤25-30%, акцент не заливка | PASS | золото через бордеры/текст; `ManualEditingPresetCard` фиолетовая заливка — единичный аут |
| Box-shadow запрещён | PASS | все `--shadow-*`=none, `shadow-*` классы — no-op |
| Noto Serif заголовки / golden | PASS на shell/ui | старые settings-клиенты заголовков `font-display` не задают (наследуют), явных sans-заголовков нет |
| Запрет неон/кислота/градиент-акцентов | FAIL (1) | `SubtitlePreview.tsx:356` violet→fuchsia градиент |

Итог: **в целом консистентно** (палитра, прямые углы по умолчанию, отсутствие теней соблюдены на уровне глобальных токенов). Один критический пробой (violet/fuchsia градиент в SubtitlePreview) и систематический долг по `rounded-full`-пилюлям. Хардкоды в массе — легитимная видео-чрома и данные бренд-кита, не стайлинг.

---

## 4. Build
`pnpm build` → **зелёный**. `✓ built in 1.00s`, все чанки собраны, 0 ошибок/0 type-ошибок в выводе сборки.

---

## Рекомендации (приоритет)
1. **CRITICAL:** заменить `SubtitlePreview.tsx:356` градиент на `bg-[color:var(--ink-3)]` (или нейтральный шахматный фон превью).
2. **MEDIUM:** заменить `rounded-full` на пилюлях-бейджах/кнопках на прямые (`card-tag`/`.btn`); оставить только функциональные статус-дотты и круговые прогресс-индикаторы.
3. **LOW:** `ManualEditingPresetCard.tsx:24` `bg-violet-600` → `--gold`/`.btn`; `ProfileSelector` `rounded-xl` → `rounded-none`; вынести score-heatmap хексы в токены.
4. **Косметика (не блокер):** постепенно мигрировать 21 файл со старого словаря токенов на `--ink/--paper/--gold/--line` для единообразия кода (цвета уже корректны через алиасы).

---

## 5. FIX LOG (BV-1 Visual Polish Surgeon) — домены job/dashboard/scheduler/projects

Хирургия: меняны только визуальные нарушения, логика/разметка не тронуты. Скоуп строго в 4 доменах. `ManualEditingPresetCard`, `SubtitlePreview`, `ProfileSelector`, `JobList` — ВНЕ моих доменов (другой агент).

### Task 1 — rounded-full на пилюлях/тегах/кнопках → rounded-none
- job/JobHero.tsx:58 (статус-бейдж), :89 (трек прогресса), :147 (StatusPill)
- job/ReelGrid.tsx:221 (фильтр-кнопка), :265 (плавающий тулбар), :281 (кнопка «Сохранить»), :290 (кнопка «Удалить»)
- job/ArtifactsAccordion.tsx:65 (тег артефакта)
- job/ReelCard.tsx:181 (трек прогресса breakdown)
- job/ClipScrubber.tsx:108 (трек range-слайдера)
- job/TinderClient.tsx:266 (таймкод), :282 («Пауза»), :486 (контейнер скорости), :497 (кнопки скорости)
- dashboard/FilterChipRow.tsx:47 (чип), :64/:65 (бейджи счётчика)
- dashboard/JobCard.tsx:128/206 (бейджи профиля), :141/:277 (статус-пилюли)
- scheduler/AccountsPicker.tsx:99 (тег сети), :114 (тег профиля)

Оставлены круглыми (исключение «истинно круглые»): дотты size-1.5 (JobHero 67/154, FilterChipRow 56, JobCard 143/215/279), score-ring ReelCard 330, play-button ClipScrubber 74, шаги PipelineTimeline 132/153/174/175/182, select-toggle/radio JobCard 231/254.

### Task 2 — кислотные/вне-палитры цвета → токены
- job/ReelCard.tsx:455-466 colorForGrade — #4ade80/#a3e635/#fde047/#fb923c/#f87171 → var(--kogane)/--gold/--copper/--mute-2/--danger
- job/TinderClient.tsx:436 — bg-neutral-500/70 text-neutral-900 → bg-[--mute]/70 text-[--ink]
- job/TinderClient.tsx:231 — bg-neutral-900 (плейсхолдер видео-карточки) → bg-[--ink-2]

### Task 3/4 — светлые хардкоды и хексы мимо токенов
- job/WaveformBar.tsx:55 — canvas "#78716c" (stone) → getComputedStyle('--mute') c fallback #8A8278 (Kasumi)
- job/PipelineTimeline.tsx:132 — text-white (danger-бейдж) → text-[--paper]; :153 — text-white (gold-бейдж) → text-[--accent-on-primary]
- job/ClipDetailClient.tsx:281 — text-white (danger-кнопка) → text-[--paper]
- dashboard/JobCard.tsx:233 — text-white (gold select-кнопка) → text-[--accent-on-primary]
- dashboard/FilterChipRow.tsx:64 — bg-white/20 на инверс-чипе → bg-black/20 (контраст на светлом активном чипе)

### Оставлено намеренно
- job/TinderClient.tsx 194/260/266/462, ReelCard.tsx 79/267/281/312/362/441/450, ClipScrubber.tsx:60 — bg-black/text-white иммерсивной видеоплеер-хромы (letterbox + оверлеи поверх видео 9:16)
- var(--chi,#8B2500) — токен danger с hex-fallback, не хардкод
- projects/ProjectFormModal.tsx:13 DEFAULT_COLOR "#C9A84C" — бренд-золото Kinzoku, дефолт пикера (brand-kit данные)
- scheduler StatusPill уже rounded-none; AccountProfilesDashboard/CaptionPresetsDashboard — rounded-md (вне scope task 1)

### Build после фиксов
`pnpm build` (apps/frontend) → ✓ built in 1.27s. 0 TS/lint ошибок.
