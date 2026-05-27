# REFACTR-13 — Удаление PRO-профиля (код, storage, UI-hooks)

> **Этап:** 02 — Бэкенд: чистка и проекты
> **Шаг:** 14 из 67
> **Зависимости:** REFACTR-03 (карта PRO-кода), REFACTR-08 (storage ADR).
> **Следующий шаг:** REFACTR-14 (Миграция модели Project)

---

## Роли

### R-BACKEND-SURGEON — Бэкенд-хирург
**Профессия:** Python-инженер, FastAPI + SQLAlchemy, 10+ лет.
**Soul:** Хирургия — не экскаватор. Удаляем только PRO, не задеваем Viral 2026 и Chapter Legacy. Каждый коммит — проверяемая операция.

### R-SERENA-OPERATOR
**Профессия:** Оператор Serena MCP.
**Soul:** Удаление символа = удаление всех его потребителей. Serena строит граф, мы режем по графу.

### R-DEVIL
**Soul:** После каждого удаления — тест. «А что если пользователь открывал PRO-проект вчера?» → миграция должна быть обратимой или переводить PRO-проекты на Viral 2026.

---

## ТРИЗ-принцип

*Принцип динамичности.* Удаление идёт снизу вверх: storage → services → API → UI. Каждый слой независимо тестируется.

---

## Оркестрация

**Режим:** Sequential. Один проход всей цепочки — один коммит. Дробление на commits внутри чанка для возможности отката.

---

## Микрозадачи

### 13.1 Прочитать карту PRO (REFACTR-03)

- [ ] Открыть `docs/audit/03-pro-removal-plan.md`.
- [ ] Пройтись по списку файлов и цитатам.

### 13.2 Миграция данных: PRO-проекты → Viral 2026

- [ ] Создать Alembic-миграцию `NNNN_remove_pro_profile.py`:
  - Перед удалением PRO из `profile_choices` — `UPDATE projects SET profile = 'viral-2026' WHERE profile = 'pro'`.
  - Логирование количества перемещённых записей.
- [ ] Downgrade migration должна восстанавливать PRO (для отката).

### 13.3 Удалить сервисы PRO

Через Serena:
- [ ] `find_symbol(name_path="ProProfile", include_body=True)` → `safe_delete_symbol` где это чистые PRO-классы.
- [ ] Проверить `profile_detector.py`, `profile_masks.py`, `account_profiles_store.py`: вырезать PRO-ветки.
- [ ] `find_referencing_symbols` после каждого удаления — убедиться что нет висящих ссылок.

### 13.4 Удалить API endpoints PRO

- [ ] `api/routes/*.py` — убрать роуты типа `/api/profiles/pro/*`.
- [ ] Убрать PRO из enum'ов Pydantic схем.

### 13.5 Удалить UI PRO

В frontend (до миграции стека — это старый Next.js, ОК):
- [ ] `ProfileSelector.tsx` — убрать опцию PRO.
- [ ] `app/settings/profiles/page.tsx` — убрать секцию PRO.
- [ ] Поиск по всему проекту (grep) `"pro"` как профиль-литерал — заменить на `"viral-2026"`.

### 13.6 Тесты

- [ ] Добавить pytest: `test_pro_profile_migration.py` — проверка что миграция работает.
- [ ] Smoke: создать проект с `profile="viral-2026"` → все pipeline-стадии работают.
- [ ] Smoke: создать проект с `profile="chapter-legacy"` → работает.

### 13.7 Verification

- [ ] `grep -ri "\"pro\"\|'pro'\|ProProfile\|\.pro\." apps/` → только легитимные совпадения (process, project).
- [ ] `alembic upgrade head` + `alembic downgrade -1` работают.

### 13.8 Commit + лог

- [ ] `git commit -m "refactor: remove PRO profile from code, storage, UI"`.
- [ ] Лог в `PIPELINE-НАВИГАТОР.md`.

### 13.9 Serena memory

- [ ] `write_memory(name="refactr-13-pro-removed", content="...")`.

---

## GATE-чекпоинт

- [ ] Миграция Alembic применяется и откатывается.
- [ ] `grep` по «pro-»/«ProProfile» чист.
- [ ] Smoke-тесты зелёные.
- [ ] Viral 2026 и Chapter Legacy работают.
- [ ] Commit создан с понятным сообщением.

**СТОП если:** миграция теряет данные пользователя → STOP-3 (спросить пользователя, что делать).

---

## Артефакт на выходе

Коммит `refactor: remove PRO profile` + Alembic-миграция + очищенный код.
