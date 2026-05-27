# Этап 03: Бэкенд — рендер и безопасность

> Статус: ⬜ Не начат
> Родитель: [[PIPELINE-НАВИГАТОР]]
> Проект: **videomaker-рефакторинг**

## Суть этапа

Два блока, идут последовательно:

### Блок 3.А — Рендер на M5 Pro (PROD-22..24)

Цель: уложить рендер в «1.5× realtime» или лучше для 60-мин видео. Сейчас путь через ffmpeg software encode — безумно долго. Нужно правильно включить **VideoToolbox** (`hevc_videotoolbox`), бенчмаркнуть, оставить software-fallback на случай недоступности (headless macOS, CI).

### Блок 3.Б — Безопасность (PROD-25..27)

Локальный сервис ≠ безопасный. Три атаки критичны:
- **Command injection** через имена файлов, попадающие в ffmpeg-строку.
- **Path traversal** через API uploads и `Finder-open`.
- **Secret leak**: `.env` с Gemini/Deepgram/Anthropic ключами — must не попадать в логи/UI-state/error-responses.

Плюс чистка debug-кода (console.log, print, временные переменные).

**Режим работы:** Sequential. Бенчмарки — с фиксацией чисел в документации.

## Подэтапы (REFACTR-21..REFACTR-26)

- **REFACTR-21** — Включить VideoToolbox HEVC encode (основной путь + software fallback) ⬜
- **REFACTR-22** — Оптимизация VBR/CRF для ≥15 Mbps при минимальном размере ⬜
- **REFACTR-23** — Бенчмарк + документ: «рендер на M5 Pro — цифры» ⬜
- **REFACTR-24** — Аудит секретов: .env guard, маски в логах, не возвращать ключи в API ⬜
- **REFACTR-25** — Аудит command injection + path traversal (ffmpeg, Finder-open, uploads) ⬜
- **REFACTR-26** — Локальный rate-limit + удаление debug-кода (print/console.log/TODO) ⬜

## Вход

- ADR-11 (видеодвижок) из Этапа 01.
- Сервисы рендера: `renderer.py`, `project_renderer.py`, `compression.py`.
- Роль **R-RENDER-ENG** + **R-SECURITY** (создаются через `role-factory` если отсутствуют в `.claude/skills/`).

## Выход

- Обновлённый рендерный путь с VideoToolbox + smoke-тест.
- 3 security-фикса применены, verified (semgrep + ручной curl).
- Документ `docs/performance/m5-render-bench.md` с цифрами.
- Документ `docs/security/local-hardening.md` с матрицей угроз/митигации.

## Инструменты

- **Context7:** документация ffmpeg, h264/hevc_videotoolbox параметры (CRF, maxrate, bufsize).
- **role-factory (`/create-role`):** R-RENDER-ENG + R-SECURITY.
- **Semgrep** (skill `static-analysis:semgrep`): важные правила для Python backend.

## GATE-чекпоинт этапа

- [ ] Рендер 60-мин видео на M5 Pro укладывается в ≤1.5× realtime (**замерено**).
- [ ] Hardware encode используется по умолчанию, fallback на software работает (подтверждено через `VIDEOTOOLBOX_DISABLED=1`).
- [ ] Semgrep по backend — 0 important findings.
- [ ] `grep -r "TODO\|FIXME\|print(" apps/backend/src` чист (кроме теста/docstring).
- [ ] `.env` не утекает ни в логи, ни в 500-responses (подтверждено тестом).
