# REFACTR-61 — .env guard + health-check

> **Этап:** 09
> **Шаг:** 62 из 67
> **Зависимости:** REFACTR-24, REFACTR-58.
> **Следующий шаг:** REFACTR-62 (E2E sce 1)

---

## Роли

### R-DEVOPS
**Soul:** Health-check — это status-page. «Работает или нет» — видно за 3 секунды.

### R-SECURITY
**Soul:** `.env` защищён. Плюс — sanity-check: ключи в `.env` не placeholders, не пустые.

---

## ТРИЗ-принцип

*Принцип предварительного действия.* Проверка работоспособности до того как пользователь попытался создать проект и получил 500.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 61.1 `.env` guard

В `run.sh`:

```bash
preflight_env() {
    if [[ ! -f .env ]]; then
        cp .env.example .env
        echo "[videomaker] .env создан из .env.example"
    fi
    
    # Простая валидация: GEMINI_API_KEY не пустой и не placeholder
    local gemkey=$(grep '^GEMINI_API_KEY=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")
    if [[ -z "$gemkey" || "$gemkey" == "YOUR_KEY_HERE" || "$gemkey" == "..." ]]; then
        echo "[videomaker] ⚠️  GEMINI_API_KEY не установлен в .env"
        echo "  Получить ключ: https://aistudio.google.com/apikey"
        echo "  Затем отредактируй .env: GEMINI_API_KEY=your_actual_key"
        # Не выход — пусть пользователь запустит и настроит через UI.
    fi
}
```

### 61.2 Backend health endpoint

`GET /api/health`:

```json
{
  "status": "ok",
  "version": "2.0.0-refactor",
  "dependencies": {
    "gemini_api": {"configured": true, "reachable": true},
    "deepgram_api": {"configured": false},
    "anthropic_api": {"configured": true, "reachable": false},
    "ffmpeg": {"available": true, "version": "7.1"},
    "videotoolbox": {"available": true}
  },
  "database": {"status": "ok", "projects_count": 47}
}
```

Реализация: проверяет наличие ключей, делает лёгкий ping к API (cache на 5 мин).

### 61.3 Health-check в UI

- В TopBar справа — индикатор: ✓ (всё ок) / ! (проблемы).
- Клик → модалка с подробностями.

### 61.4 Health-check script

`scripts/health-check.sh`:

```bash
#!/bin/bash
set -e
STATUS=$(curl -s http://127.0.0.1:8000/api/health | jq -r '.status')
if [[ "$STATUS" == "ok" ]]; then
    echo "✓ OK"
    exit 0
else
    echo "✗ FAIL"
    curl -s http://127.0.0.1:8000/api/health | jq
    exit 1
fi
```

Использование: в CI, в `./run.sh --verify`, в debugging.

### 61.5 Commit + Serena + лог

### 61.6 Итог Этапа 09

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 09 ЗАВЕРШЁН. DevX готов.»

---

## GATE-чекпоинт

- [ ] `.env` guard работает (missing → copy from example + warning).
- [ ] `/api/health` endpoint возвращает детали.
- [ ] UI индикатор работает.
- [ ] `scripts/health-check.sh` возвращает 0 / non-zero.
- [ ] **Этап 09 ЗАВЕРШЁН.**

---

## Артефакт на выходе

`.env` guard в run.sh + health endpoint + UI indicator + скрипт.
