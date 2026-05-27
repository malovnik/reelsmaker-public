# REFACTR-65 — Документация: README + ARCHITECTURE + USER-GUIDE

> **Этап:** 10
> **Шаг:** 66 из 67
> **Зависимости:** Все предыдущие.
> **Следующий шаг:** REFACTR-66 (Release checklist)

---

## Роли

### R-UX-WRITER
**Soul:** Документация — часть продукта. README за 30 секунд должен объяснить «что это и как запустить».

### R-ARCHITECT
**Soul:** ARCHITECTURE документирует не текущее состояние, а принципы — почему так сделано, чтобы через год не переизобрести.

---

## ТРИЗ-принцип

*Принцип копирования.* ADR + C4-диаграммы (Этап 01) + docs из аудита (Этап 00) = скелет архитектурного документа. Собираем, не изобретаем.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 65.1 README.md (корневой)

Структура:

```markdown
# videomaker

Локальное приложение для автоматической нарезки длинных видео на рилсы/шортсы 9:16. Для MacBook Pro M5 Pro, 24 GB RAM.

## Что делает

Приходит видео 30-90 минут → уходит N готовых рилсов 9:16 HEVC 15 Mbps.

Пайплайн: транскрибация → удаление тишины → мульти-проход LLM → генерация идей → approve/reject/regenerate → склейка → color+subtitles+B-roll → рендер.

## Запуск

```bash
./run.sh
```

Открыть http://localhost:3000

## Требования

- macOS (Apple Silicon, рекомендовано M-series)
- ffmpeg 6+
- uv (Python package manager)
- pnpm
- node 20+
- API-ключи: Gemini (обязательно), Deepgram/Anthropic/OpenAI (опционально)

## Документация

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — как устроено
- [USER-GUIDE.md](docs/USER-GUIDE.md) — как пользоваться
- [docs/adr/](docs/adr/) — архитектурные решения
- [docs/performance/m5-render-bench.md](docs/performance/m5-render-bench.md) — цифры
```

### 65.2 docs/ARCHITECTURE.md

Собрать:
- Обзор (1-2 страницы): цели, ограничения, non-goals.
- C4 диаграммы (из REFACTR-12).
- Стек + обоснование (ссылки на ADR).
- Структура папок.
- Data flow (new project → rendered clip).
- Обработка ошибок и восстановление.

### 65.3 docs/USER-GUIDE.md

Руководство для владельца:
- Первый запуск (установка ключей, запуск run.sh).
- Создание проекта.
- Работа с идеями (approve/reject/regenerate).
- Настройки (краткий обзор каждой группы).
- Cmd+K горячие клавиши.
- Troubleshooting (OOM не будет, но VideoToolbox, 422 ошибки валидации, 503 если .env не настроен).

### 65.4 Обновить CLAUDE.md проекта

- Обновить описание стека (Vite, не Next.js).
- Обновить команды (run.sh + health-check.sh).
- Обновить философию (минималистично, без клише).

### 65.5 CHANGELOG.md

Заполнить релиз v2.0-refactor:

```markdown
# v2.0-refactor — 2026-04-XX

## Большой рефакторинг

### Changed
- Frontend stack: Next.js → Vite 6 + React 19 + TanStack Router + TanStack Query.
  - RAM dev-server: 12 ГБ → ~400 МБ.
- Дизайн-система переизобретена (docs/design/MANIFEST.md).
- Темы: dark (default) + light, persist в localStorage + backend.
- Настройки реструктурированы: 8 страниц → 7 групп (docs/audit/02-settings-inventory.md).

### Added
- Автосохранение настроек проекта (debounce 10 с).
- Переиспользование настроек между проектами (copy-from).
- Перезапуск pipeline с произвольного шага.
- Поток идей рилсов с approve/reject/regenerate перед рендером.
- Cmd+K Command Palette.
- VideoToolbox HEVC encode (рендер на M5 ≤1.5× realtime).
- Простой / Экспертный режим UI.

### Removed
- Профиль PRO (удалён из кода, UI, storage). Оставлены: Viral 2026 (default) + Chapter Legacy.
- Next.js (полностью).
- Horizontal scroll в Settings/Subtitles.

### Fixed
- OOM при dev-запуске (12 ГБ heap limit не нужен).
- Cmd+K поиск — теперь работает.
- Автосохранение настроек — ранее отсутствовало.
```

### 65.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] README корневой обновлён.
- [ ] docs/ARCHITECTURE.md создан и отражает текущее.
- [ ] docs/USER-GUIDE.md создан.
- [ ] CLAUDE.md обновлён.
- [ ] CHANGELOG.md v2.0-refactor.
- [ ] Все ссылки в README работают.

---

## Артефакт на выходе

Пакет документации v2.0-refactor.
