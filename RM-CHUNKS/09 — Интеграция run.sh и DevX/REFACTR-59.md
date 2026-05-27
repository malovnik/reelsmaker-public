# REFACTR-59 — run.sh startup: Vite-dev + trap SIGINT/TERM/EXIT

> **Этап:** 09
> **Шаг:** 60 из 67
> **Зависимости:** REFACTR-58 (preflight), REFACTR-31 (Vite).
> **Следующий шаг:** REFACTR-60 (Логи)

---

## Роли

### R-DEVOPS
**Soul:** Процессы-сироты — классический инцидент Mac-разработки. Trap на все сигналы, kill дерева — принципиально.

### R-BACKEND-SURGEON (консультативно)
**Soul:** Backend uvicorn — reload mode, frontend Vite — dev mode. Они не знают друг о друге. Координирует shell.

---

## ТРИЗ-принцип

*Принцип копирования.* Текущий `run.sh` уже многое делает правильно (preflight-kill для stale uvicorn/next). Копируем его структуру, заменяем `next dev` на `vite dev`.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 59.1 Preflight-kill patterns (обновить под Vite)

```bash
preflight_kill "uvicorn videomaker.main" "uvicorn workers"
preflight_kill "uv run uvicorn" "uv-run wrappers"
preflight_kill "vite" "vite dev"
preflight_kill "esbuild" "esbuild workers"
preflight_kill "pnpm.*dev" "pnpm wrappers"
preflight_kill "ffmpeg.*data/artifacts" "residual ffmpeg renders"
```

Убрать: `next dev`, `next-server`, `turbopack`, `.next/dev/lock` cleanup.

### 59.2 Preflight_free_port (3000, 8000)

Оставить как есть.

### 59.3 Startup

```bash
(
    cd "$ROOT_DIR/apps/backend"
    exec uv run uvicorn videomaker.main:app \
        --host "${APP_HOST:-127.0.0.1}" \
        --port "${APP_PORT:-8000}" \
        --reload --reload-dir src \
        --reload-exclude "**/__pycache__/*" \
        --reload-exclude "**/*.pyc" \
        --log-level "${APP_LOG_LEVEL:-info}"
) &
BACKEND_PID=$!

(
    cd "$ROOT_DIR/apps/frontend"
    exec pnpm dev -- --host 127.0.0.1 --port "${FRONTEND_PORT:-3000}"
) &
FRONTEND_PID=$!
```

### 59.4 Trap cleanup

```bash
cleanup() {
    echo ""
    echo "[videomaker] останавливаю процессы…"
    [[ -n "$BACKEND_PID" ]] && kill -TERM "$BACKEND_PID" 2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    sleep 2
    pkill -9 -f "uvicorn videomaker.main" 2>/dev/null || true
    pkill -9 -f "uv run uvicorn" 2>/dev/null || true
    pkill -9 -f "vite" 2>/dev/null || true
    pkill -9 -f "esbuild" 2>/dev/null || true
    pkill -9 -f "pnpm.*dev" 2>/dev/null || true
    # Убить всех детей ffmpeg от этого pipeline (но не системные)
    pkill -9 -f "ffmpeg.*data/artifacts" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "[videomaker] выход"
}
trap cleanup EXIT INT TERM
```

### 59.5 Удалить next-специфичное

- Больше нет `rm -f apps/frontend/.next/dev/lock`.
- Добавить очистку `apps/frontend/node_modules/.vite/` если был corrupted cache:
  ```bash
  rm -rf "$ROOT_DIR/apps/frontend/node_modules/.vite" 2>/dev/null || true
  ```

### 59.6 pycache cleanup (оставить)

```bash
find "$ROOT_DIR/apps/backend/src" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
```

### 59.7 Smoke

- [ ] `./run.sh` → оба процесса стартуют.
- [ ] Ctrl+C → через 5 с нет процессов:
  ```bash
  ps aux | grep -E "uvicorn|vite|pnpm" | grep -v grep
  ```
  пусто.
- [ ] Повторный `./run.sh` не конфликтует.

### 59.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Запуск работает.
- [ ] Ctrl+C убивает всё дерево.
- [ ] Порты освобождены.
- [ ] Повторный запуск идемпотентен.

---

## Артефакт на выходе

Обновлённый `run.sh` — startup-секция.
