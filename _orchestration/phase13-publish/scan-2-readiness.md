# Scan 2 — Public-Release Readiness (PII / приватные данные / медиа)

> Аудитор: Public-Release Readiness Auditor. Скоуп: всё, КРОМЕ ключей/секретов (их сканирует отдельный агент).
> Дата: 2026-05-27. Репо: `reelsmaker-public` (private → public).

## ВЕРДИКТ: НЕ ГОТОВО

Блокеров безопасности (утечка секретов/медиа/БД) нет. Но в трекаемых файлах много **PII и личных путей**, которые не должны попасть в публичный репозиторий. Требуется чистка перед публикацией.

---

## 1. КРИТИЧНО — Личные данные / PII (чистить обязательно)

### 1.1 Email владельца в коде
- `apps/backend/pyproject.toml:8` — `{ name = "malovnik", email = "<redacted-email>" }`. Реальный email в публичном пакете. Заменить на нейтральное authors или убрать email.

### 1.2 Локальные пути `~/...` — 116 вхождений в 24 файлах
Раскрывают username, структуру личного диска, путь к Obsidian-ваулту и приватным планам.
- **Код/конфиг:** `README.md:7` (`~/.claude`), `CONTEXT.md:55`.
- **Документация:** `docs/guide.md`, `docs/plans/2026-04-2*.md` (×4), `docs/diagnostics/.../evidence-inventory.md` (раскрывает `~/.local/bin`, `~/.npm-global`), `docs/superpowers/plans/*`, `docs/top-down-e2e-validation-guide.md`, `docs/vision-profiles-redesign-task.md`, `docs/production-features-plan.md`, `docs/reelibra-redesign-roadmap.md`, `idea.md`.
- **RM-CHUNKS/** (×8 файлов): `task.md`, `README.md`, `PIPELINE-RALPH-PROMPT.md`, `PIPELINE-НАВИГАТОР.md`, `00 — .../00-АУДИТ.md`, `REFACTR-00.md`.
- **_orchestration/**: `00-ROADMAP.md`, `phase12-final-validation/c1-v2-frontend.md`.
- Особо чувствительно: путь к Obsidian-ваулту `…/malovnik-obsidian/🤖 ИИ/Софт/looper-tmux` и `…/😎 Бизнес/БрендБук` (раскрывает приватную организацию рабочих файлов).

Рекомендация: глобальная замена `<source-repo>` → относительные пути или `<repo-root>`; убрать упоминания ваулта/`.claude/plans` целиком.

### 1.3 Реальное имя владельца «Никита / Малов Никита»
Раскрывает личность заказчика как single-user. Вхождения:
- `RM-CHUNKS/task.md:4` — «**Заказчик:** Малов Никита (владелец-единственный пользователь)».
- `RM-CHUNKS/.../REFACTR-12.md:37`, `PIPELINE-НАВИГАТОР.md:163`.
- `docs/architecture/c4-overview.md` (×4: actor «Никита — владелец»).
- `_orchestration/phase1b-stub-audit/STUB-REALITY-MAP.md:56` («Nikita, рилсы из Азии»), `phase9-redesign/agent-specs/d1,d2,d4,d5` («брендбук Никиты Малова», «侍 НИКИТА · REELS»).
- В коде: `apps/backend/src/videomaker/services/reels_composer.py:9,1947` («формула Никиты», «Критерии Никиты») — это код, попадёт в публику.
- `apps/backend/src/videomaker/services/prompts.py:99` — ссылка на личный файл Obsidian «…Основная версия.md (malovnik-obsidian)».

Рекомендация: «Никита/Малов» → «владелец/single-user/the author»; убрать ссылку на Obsidian-файл в prompts.py.

### 1.4 Соц-аккаунты (мокап, низкий риск, но проверить)
- `_orchestration/phase9-redesign/agent-specs/d5-screens.md:350-351` — `@nikita.reels` (TikTok), `@nikita` (Instagram). Это ASCII-вайрфрейм-плейсхолдеры, не реальные подключённые аккаунты, но дублируют имя — желательно заменить на `@your_handle`.

---

## 2. Чувствительный контент (RM-CHUNKS / docs / _orchestration)

- **Брендбук НЕ скопирован в репо целиком** — подтверждено. Tracked-файлов с исходником брендбука нет (`grep` по именам `website-style/БрендБук/brandbook` = только аудит-отчёт и frontend-компоненты BrandKit).
- `_orchestration/phase12-final-validation/c2-v2-brandbook-ux.md` — это **аудит-отчёт** UI на соответствие брендбуку, не сам брендбук. Цитирует палитру/шрифты (латунь `#C9A84C` на `#0A0A0A`, Noto Serif JP / Press Start 2P) — это уже воплощено в публичном `globals.css`/`fonts.ts`, не является коммерческой тайной. ОК для публикации.
- Дизайн-спеки в `_orchestration/phase9-redesign/agent-specs/` и `RM-CHUNKS/05/` описывают визуальный язык — производный от брендбука, но не его проприетарный исходник. ОК (после чистки имени «Никита»).
- Коммерческой тайны / личных заметок Никиты сверх вышеперечисленного не обнаружено.

## 3. Данные / медиа в трекаемых — ЧИСТО

- `git ls-files` по `.db/.mp4/.mov/.sqlite/data/`: совпадения только **ложные** (`services/prompts_data/*.md` — каталог промптов, не `data/`). Реальных медиа/БД нет.
- `data/` (включая `data/videomaker.db`, 577 КБ) **существует на диске, но НЕ трекается** — корректно покрыто `.gitignore` (`/data/`). Подтверждено `git ls-files data/` = пусто.
- Реальный `.env` не трекается; трекается только `.env.example`.

## 4. .gitignore — АДЕКВАТЕН

Покрывает: `.env`/`.env.*.local`/`*.local`, `/data/`, все медиа-расширения (`*.mp4/mov/mkv/webm/avi/wav/mp3/m4a`), `*.db/*.sqlite*`, веса моделей (`*.gguf/*.safetensors/*.onnx/*.bin`), `uploads/outputs/renders/tmp/cache`, `.claude/`, `.serena/`, `Референсы/`, `будущие фичи.md`. Замечаний нет.

## 5. README / доки

- **Секретов/токенов в примерах команд нет.** `.env.example` — все значения плейсхолдеры или безопасные дефолты (`APP_HOST=127.0.0.1`, публичные base-URL вроде `https://api.z.ai/...`, имена моделей). Реальных ключей нет.
- Внутренних доменов / non-local IP не найдено (только `localhost`/`127.0.0.1`).
- Единственная проблема README — личный путь в строке 7 (см. 1.2).

## 6. _orchestration отчёты — секретов нет

- Все упоминания `API_KEY/secret/token` — это **имена env-переменных и инструкции** (`DEEPGRAM_API_KEY`, `mask_secrets` processor, тестовая строка `sk-abcdef123456789012345` как пример маскирования). Реальных значений ключей ни один агент не процитировал.
- Приватные данные в отчётах = те же имя «Никита» и пути `~` (учтены в разделе 1).

---

## ЧЕК-ЛИСТ ПЕРЕД PUBLIC

1. [ ] `apps/backend/pyproject.toml` — убрать реальный email (1.1).
2. [ ] Глобально заменить `~/...` → относительные/`<repo-root>`; удалить ссылки на `.claude/plans` и Obsidian-ваулт (1.2) — 24 файла.
3. [ ] Заменить «Никита / Малов Никита» → «владелец/single-user» в коде (`reels_composer.py`, `prompts.py`) и доках (1.3).
4. [ ] Заменить мокап-хэндлы `@nikita*` в `d5-screens.md` (1.4) — опционально.
5. [x] Медиа/БД/`data/` не трекаются — OK.
6. [x] `.gitignore` адекватен — OK.
7. [x] `.env.example` без секретов — OK.
8. [x] Брендбук-исходник в репо отсутствует — OK.
