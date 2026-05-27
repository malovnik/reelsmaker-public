# REFACTR-24 — Аудит секретов (.env guard, маски в логах)

> **Этап:** 03
> **Шаг:** 25 из 67
> **Зависимости:** REFACTR-21..23 (рендер-блок закрыт).
> **Следующий шаг:** REFACTR-25 (command injection + path traversal)

---

## Роли

### R-SECURITY — Аудитор безопасности
**Профессия:** Security engineer, специализация на Python-бэкендах и локальных сервисах.
**Soul:** Локальный ≠ безопасный. `.env` может утечь через логи, error-responses, скриншоты, git-history. Каждая утечка — инцидент.

### R-ROLE-FACTORY
**Профессия:** Оркестратор role-factory skill.
**Soul:** Если роль R-SECURITY ещё не создана как переиспользуемый skill — создать через `/create-role security-auditor` перед стартом чанка.

---

## ТРИЗ-принцип

*Принцип сегментации.* Секреты должны быть изолированы: `.env` → `pydantic-settings` → Python `Settings` класс → никогда напрямую в коде/логах/responses.

---

## Оркестрация

**Режим:** Sequential. Обязательно активация `role-factory:security-auditor` skill.

---

## Микрозадачи

### 24.1 Активация skill security-auditor

- [ ] `Skill: role-factory:security-auditor` — если не активирован.
- [ ] Если роль не существует в `.claude/skills/` — запустить `role-factory:create-role` для её создания.

### 24.2 Найти все точки доступа к секретам

Через Serena:
- [ ] `search_for_pattern(pattern="os\\.environ|getenv|settings\\.[A-Z_]+")` — все места чтения переменных окружения.
- [ ] Зафиксировать таблицу: файл:строка — какой ключ — куда используется.

Список ожидаемых секретов:
- `GEMINI_API_KEY`
- `DEEPGRAM_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `ZHIPU_API_KEY` (если есть)

### 24.3 Проверка .env.example

- [ ] `.env.example` содержит ТОЛЬКО placeholders, никаких реальных ключей.
- [ ] `.env` в `.gitignore` (подтвердить).
- [ ] `git log --all -- .env` — нет в истории.

### 24.4 Логирование — маски

- [ ] structlog processor: добавить `mask_secrets` processor, который зашумляет любое значение длиной 20+ символов, похожее на ключ.
- [ ] Тест: отправить в лог «logger.info('got key', key='sk-abcdef123456789012345')» → в output «key='sk-****'».

### 24.5 Error responses

- [ ] FastAPI exception handlers: никогда не возвращают `os.environ` или `settings.model_dump()`.
- [ ] При 500 — `{"error": "internal"}`, никаких tracebacks в prod-режиме.
- [ ] В dev — tracebacks ОК, но пройти ещё раз через mask_secrets.

### 24.6 Frontend: не проксировать ключи

- [ ] `GET /api/settings/connections` — возвращает `{has_gemini_key: true, has_deepgram_key: false}`, **не сами ключи**.
- [ ] UI для установки ключа — POST отдельный, ключ никогда не возвращается назад.

### 24.7 Verification

- [ ] Semgrep Python — 0 important findings.
- [ ] Ручной тест: установить фейковый ключ → вызвать эндпоинт с ошибкой → проверить что ключ не в ответе.
- [ ] `grep -r "sk-\|AIza\|sk_" apps/backend/src apps/frontend/src` → пусто (кроме тестовых fixtures с `sk-TEST-*`).

### 24.8 Документ

`docs/security/secrets-handling.md`.

### 24.9 Commit + Serena

---

## GATE-чекпоинт

- [ ] Все секреты идут только через pydantic-settings.
- [ ] Mask-processor работает (тест).
- [ ] Error-handlers не утекают секретов.
- [ ] Frontend не знает ключей (только наличие).
- [ ] Документ создан.

---

## Артефакт на выходе

Mask-processor + обновлённые handlers + документ по secrets-handling.
