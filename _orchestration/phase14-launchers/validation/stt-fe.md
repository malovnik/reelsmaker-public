# STT Frontend Validation — Cross-Platform (Windows lens)

**Verdict: PASS**

Доказано: Windows-пользователь во фронте физически не может выбрать ничего, кроме Deepgram (а при пустом списке — вообще ничего, только инструкция про ключ). Все STT-селекторы рендерятся исключительно из `models.available_transcribers` (бэкенд = `/api/v1/health.transcribers`). Хардкод-списка движков в JSX нет.

## 1. Селекторы рендерят опции из бэкенда (без хардкод-списка)

Все три точки выбора STT итерируют ровно `models.available_transcribers`:

| Место | Код | Источник опций |
|---|---|---|
| GuidedFlow S6 (Пошаговый) | `transcribers.map((t) => <RadioCard ... title={transcriberLabel(t)} />)` (GuidedFlow.tsx:630-638) | `const transcribers = models.available_transcribers` (607) |
| UploadWizard (Эксперт) | `models.available_transcribers.map((t) => ({ value: t, label: transcriberLabel(t) }))` (UploadWizard.tsx:652-655) | бэкенд |
| ModelsPage | `available.map((key) => ... transcriberLabel(key))` (ModelsPage.tsx:107-122) | `available={info.available_transcribers}` (64) |

Тип-контракт: `available_transcribers: string[]` объявлен в `lib/api/settings.ts:8` (часть `ModelsInfo`) — приходит с бэкенда, не константа фронта. Файл `lib/constants/transcribers.ts` явно документирует: «Фронт НЕ хардкодит список: показывает ровно то, что вернул бэкенд».

## 2. Симуляция Windows: `available_transcribers = ["deepgram"]`

Поскольку каждый селектор делает `.map()` по массиву из одного элемента `"deepgram"`, рендерится РОВНО одна опция — Deepgram. MLX-опций нет нигде: статичного списка из 3 движков в обход массива в JSX не существует (проверено чтением всех трёх блоков). Лейбл-/хинт-карты (`TRANSCRIBER_LABEL`, `TRANSCRIBER_DESC`) — это `Record<string,string>` lookup по id, обращение только через `transcriberLabel(t)` / `TRANSCRIBER_DESC[t]` для тех id, что бэкенд реально вернул. На Windows ключи `stable_ts_mlx`/`mlx_whisper` — мёртвые ключи карты, никогда не итерируются и не рендерятся.

## 3. Пустой список (`[]`, Windows без ключа Deepgram)

Все три селектора гейтят рендер на `length > 0`, иначе показывают `NO_TRANSCRIBER_MESSAGE`:
- GuidedFlow.tsx:628 `transcribers.length > 0 ? <radiocards> : <NO_TRANSCRIBER_MESSAGE>`
- UploadWizard.tsx:648 `models.available_transcribers.length > 0 ? <Select> : <NO_TRANSCRIBER_MESSAGE>`
- ModelsPage.tsx:105 `available.length > 0 ? <dl> : <NO_TRANSCRIBER_MESSAGE>`

Сообщение (transcribers.ts:26): «Для распознавания речи на Windows/Linux нужен ключ Deepgram (настройки → .env). На macOS работает локально без ключа.» Выбрать нельзя — рендерится текст, не контрол. Onboarding.tsx:55,61 дополнительно гейтит готовность по `health.transcribers.length > 0` (readiness-проверка, не выбор).

## 4. useWizardState: дефолт и stale-выбор

- Дефолт = первый доступный: `const defaultTranscriber = models.available_transcribers[0] ?? ""` (useWizardState.ts:195). На Windows c `["deepgram"]` → дефолт `"deepgram"`; на пустом → `""`.
- Stale-выбор переключается на доступный (effect, строки 204-209): если текущий `transcriber` не входит в `available_transcribers` (напр. stale `stable_ts_mlx`, сохранённый на Mac и открытый на Windows) и список непуст — `setTranscriber(list[0])`. Так в `POST /jobs` (`form.append("transcriber", transcriber)`, строка 311) не уйдёт движок, который бэкенд отклонит.

## 5. Остаточные хардкоды "stable_ts_mlx"/"mlx_whisper"

`grep -rn "stable_ts_mlx\|mlx_whisper" src` → 6 совпадений, все безопасны:

| Файл:строка | Контекст | Опасность |
|---|---|---|
| `lib/constants/transcribers.ts:13-14` | ключи `TRANSCRIBER_LABEL` (lookup-карта) | нет — обращение только по id из бэкенда |
| `components/upload/guided/GuidedFlow.tsx:41-42` | ключи `TRANSCRIBER_DESC` (lookup-карта) | нет — `TRANSCRIBER_DESC[t]` для t из бэкенда |
| `components/upload/useWizardState.ts:201` | комментарий про stale-логику | нет — комментарий |
| `components/settings-shared/controlHints.ts:313-314` | статический help-текст тултипа поля `transcriber` (what/effect/advise) | минорно — см. ниже |

Единственное место, где Windows-юзер может УВИДЕТЬ слова mlx — статический тултип-хинт поля «Распознавание речи» (`controlHints.ts`), который рендерится независимо от платформы и упоминает mlx как пояснение («locally on Mac»). Это чисто информационный текст в подсказке, НЕ выбираемая опция — выбрать mlx он не даёт. Функциональной утечки нет. При желании можно сделать хинт платформо-зависимым, но это косметика, не баг.

## 6. Build gate

`pnpm build` (apps/frontend) — зелёный: `✓ built in 1.09s`, 0 ошибок TS/сборки. Отдельный чанк `transcribers-CYZzr6TB.js` (0.46 kB) собрался.

---

**Итог:** На Windows фронт показывает только то, что вернул бэкенд. С `["deepgram"]` — только Deepgram; с `[]` — только инструкция про ключ, выбор невозможен. MLX не появляется ни в одном селекторе. Дефолт и stale-guard корректны. Единственный остаточный mlx-упоминание — статический тултип-хинт (информация, не контрол). Build зелёный.
