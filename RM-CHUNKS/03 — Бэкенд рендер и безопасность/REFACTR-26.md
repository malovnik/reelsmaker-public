# REFACTR-26 — Локальный rate-limit + чистка debug-кода

> **Этап:** 03
> **Шаг:** 27 из 67
> **Зависимости:** REFACTR-24, REFACTR-25.
> **Следующий шаг:** REFACTR-27 (Инициализация Vite)

---

## Роли

### R-SECURITY
**Soul:** Даже локальный сервис должен иметь rate-limit. Баг в фронте → 1000 запросов в секунду → LLM-счёт прилетит.

### R-BACKEND-SURGEON
**Soul:** Debug-код — следы работы, не код. Перед закрытием бэкенд-этапа — всё чистится. Принципиально.

---

## ТРИЗ-принцип

*Принцип отбрасывания.* Всё что не живой продакшн-код — убрать. Debug-комментарии, `print()`, закомментированные блоки, stale TODO без номера задачи.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 26.1 Rate-limit

- [ ] `slowapi` или `fastapi-limiter` — Context7 рекомендация.
- [ ] Default: 60 requests/min для обычных endpoints, 10 requests/min для LLM-heavy (regenerate).
- [ ] Без авторизации — ключ клиента по IP (всегда 127.0.0.1 для локалки, но rate-limit всё равно работает per-IP).

### 26.2 Чистка debug-кода

Через Serena `search_for_pattern`:
- [ ] `print(` — все в backend Python (должно быть 0 в production-коде, OK в tests).
- [ ] `console.log(` — во frontend (OK только в dev-помощниках, или переведено в logger).
- [ ] `TODO|FIXME|XXX|HACK` — все должны исчезнуть или иметь ссылку на GitHub issue.
- [ ] Закомментированные блоки кода — удалить.

### 26.3 Ruff/ESLint строгость

- [ ] Ruff config: добавить правила запрета `print` в production (`T201` exclude `tests/`).
- [ ] ESLint config: `no-console` на frontend (кроме явных утилит).
- [ ] Прогнать `ruff check apps/backend` и `pnpm lint` — 0 errors.

### 26.4 Структурированные логи

- [ ] Заменить все `logger.info("blah blah {var}")` на `logger.info("event_name", var=var)` (structlog style).
- [ ] Единый формат: `{timestamp, level, event, **context}`.

### 26.5 Verification

- [ ] `grep -r "print(\|console\.log\|TODO\|FIXME" apps/` → 0 в продакшн-коде.
- [ ] Rate-limit работает (curl-тест на 100 rapid requests → 429).

### 26.6 Commit + Serena + лог

### 26.7 Итог Этапа 03

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 03 ЗАВЕРШЁН. Рендер + безопасность. Бэкенд готов к фронт-миграции».

---

## GATE-чекпоинт

- [ ] Rate-limit работает.
- [ ] Все debug-следы убраны.
- [ ] Ruff/ESLint 0 errors.
- [ ] Логи структурированные.
- [ ] **Этап 03 ЗАВЕРШЁН.**

---

## Артефакт на выходе

Rate-limit middleware + чистый код + строгие linter-ы.
