# REFACTR-66 — Финальный release-чеклист + тег git

> **Этап:** 10
> **Шаг:** 67 из 67 (финальный)
> **Зависимости:** Все предыдущие 66 чанков завершены.
> **Следующий шаг:** — (проект готов)

---

## Роли

### R-ARCHITECT
**Soul:** Last-mile. Всё что собрано — запечатываем. Ничего не оставляем «на потом».

### R-QA
**Soul:** Ещё раз прогон по всем критериям — глазами, не логикой.

### R-DEVIL
**Soul:** Последний шанс найти что-то плохое. Крутим педаль сомнения до конца.

---

## ТРИЗ-принцип

*Принцип идеального результата.* Идеальный релиз — тот, после которого владелец открывает приложение и говорит «всё как я просил». Проверяем это напрямую.

---

## Оркестрация

**Режим:** Sequential + человек (владелец).

---

## Микрозадачи

### 66.1 Финальный чеклист

Проверить пункт за пунктом:

**Frontend:**
- [ ] Next.js удалён (0 ссылок в коде, 0 в package.json).
- [ ] Vite dev idle RAM <500 МБ (замер: `ps -o rss -p $(pgrep vite)`).
- [ ] Тёмная тема по умолчанию. Светлая альтернатива. Persist работает.
- [ ] Главная — Студия с grid проектов.
- [ ] Контекстное меню карточки: rename, soft-delete, hard-delete, Finder-open — все работают.
- [ ] Новый проект: drop-zone + выбор настроек + создание.
- [ ] Копирование настроек из предыдущего + picker.
- [ ] Workbench: timeline стадий + restart-from-step.
- [ ] Идеи: grid + approve/reject/regenerate + custom prompt.
- [ ] Рендер: прогресс + clips grid + download.
- [ ] Настройки: 7 групп без horizontal scroll.
- [ ] Cmd+K работает везде.
- [ ] Simple/Expert режим.

**Backend:**
- [ ] PRO-профиль удалён (grep пусто).
- [ ] Viral 2026 + Chapter Legacy — работают.
- [ ] API автосохранения (PUT settings) + conflict-detection.
- [ ] Restart API.
- [ ] Ideas API (generate + approve/reject/regenerate).
- [ ] Copy-from API.
- [ ] Finder-open + soft-delete + hard-delete.
- [ ] Rate-limit.
- [ ] Health endpoint.
- [ ] Логи унифицированы.

**Рендер:**
- [ ] VideoToolbox HEVC работает по умолчанию.
- [ ] Software fallback работает.
- [ ] Бенчмарк: ≤1.5× realtime на M5.
- [ ] Output ≥15 Mbps.

**Безопасность:**
- [ ] Секреты не в логах, не в ответах API.
- [ ] Path traversal — заблокирован.
- [ ] Command injection — невозможен (argv-only).
- [ ] Semgrep + grep: 0 критических.

**DevX:**
- [ ] `./run.sh` на чистой системе — подсказывает установку deps.
- [ ] Ctrl+C убивает всё.
- [ ] `.env` guard.
- [ ] Health-check script.

**Документация:**
- [ ] README + ARCHITECTURE + USER-GUIDE + CHANGELOG.
- [ ] Все 5 ADR + C4 диаграммы.
- [ ] CLAUDE.md актуален.

**E2E:**
- [ ] Smoke #1 (новый проект full) — прошёл.
- [ ] Smoke #2 (copy-from) — прошёл.
- [ ] Smoke #3 (restart) — прошёл.

### 66.2 Semgrep финальный проход

- [ ] `semgrep` по backend (important-only).
- [ ] 0 high/critical.
- [ ] Отчёт сохранён в `docs/security/semgrep-final-YYYY-MM-DD.sarif`.

### 66.3 Grep на мусор

```bash
grep -r "TODO\|FIXME\|XXX\|HACK" apps/  # 0 результатов
grep -r "print(\|console\.log(" apps/   # 0 в продакшн-коде
grep -r "\"pro\"\|'pro'\|ProProfile" apps/  # 0
```

### 66.4 Финальная проверка владельцем

- [ ] Запустить `./run.sh`.
- [ ] Владелец открывает http://localhost:3000.
- [ ] Проходит пару сценариев сам (создать проект, изменить настройки, перезапустить).
- [ ] Владелец подтверждает: «как просил».

**Если владелец говорит «нет» — вернуться к соответствующему чанку, пофиксить, retry.**

### 66.5 Git тег

```bash
git tag -a v2.0-refactor -m "Полный рефакторинг: Vite стек, дизайн-система, автосохранение, идеи рилсов, VideoToolbox"
git push origin v2.0-refactor
```

### 66.6 Финальный лог

В `PIPELINE-НАВИГАТОР.md` добавить:

```
| 2026-04-XX | Чанк 67/67: REFACTR-66 «Финальный чеклист» ✅. 
Все 67 чанков пройдены. Git-тег v2.0-refactor создан. 
Владелец подтвердил готовность. Проект завершён. |
```

В таблице статусов этапов — все этапы 00-10 отмечены ✅.

### 66.7 Serena memory — финальный

- [ ] `write_memory(name="refactr-project-completed", content="videomaker v2.0 released. All 67 chunks done. Tag v2.0-refactor. Ключевые метрики: RAM 400MB, рендер 1.2× realtime на M5, ..., подтверждено владельцем.")`.

### 66.8 (опционально) Schedule follow-up

Предложить владельцу: `/schedule` через 2 недели — проверить как приложение себя ведёт в реальной работе, открыть PR с мелкими фиксами.

---

## GATE-чекпоинт (последний)

- [ ] Все пункты чеклиста ✅.
- [ ] Semgrep чист.
- [ ] Grep чист.
- [ ] Владелец подтвердил.
- [ ] Git-тег создан и запушен.
- [ ] Навигатор и memory обновлены.
- [ ] **ПРОЕКТ ЗАВЕРШЁН.**

---

## Артефакт на выходе

Git-тег `v2.0-refactor` + финальный checklist + подтверждение владельца.

---

🎬 **videomaker v2.0 — релиз.**
