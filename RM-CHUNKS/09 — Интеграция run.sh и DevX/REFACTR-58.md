# REFACTR-58 — run.sh preflight: deps check + install

> **Этап:** 09 — Интеграция: run.sh и DevX
> **Шаг:** 59 из 67
> **Зависимости:** REFACTR-31 (Vite stack).
> **Следующий шаг:** REFACTR-59 (startup + trap)

---

## Роли

### R-DEVOPS — DevOps-инженер локального стека
**Профессия:** Shell-скриптер, mac-админ.
**Soul:** Preflight-скрипт — первое впечатление о проекте. Если падает на чистой машине — проект «для своих». Должен работать для любого, кто клонирует репо.

### R-DEVIL
**Soul:** «А если `uv` не установлен? А если `pnpm`? А если `ffmpeg`? А если нет `.env`?» — каждая развилка закрыта.

---

## ТРИЗ-принцип

*Принцип предварительного действия.* Preflight — всё что нужно сделать перед startup. Вcё идемпотентно. Повторный запуск не ломает.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 58.1 Проверка зависимостей

В `run.sh` секция `preflight_check_deps()`:

```bash
preflight_check_deps() {
    local missing=()
    command -v uv >/dev/null || missing+=("uv")
    command -v pnpm >/dev/null || missing+=("pnpm")
    command -v ffmpeg >/dev/null || missing+=("ffmpeg")
    command -v node >/dev/null || missing+=("node")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "[videomaker] отсутствуют зависимости: ${missing[*]}"
        echo "  uv:     curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  pnpm:   brew install pnpm || npm install -g pnpm"
        echo "  ffmpeg: brew install ffmpeg"
        echo "  node:   brew install node"
        exit 1
    fi
}
```

### 58.2 Проверка версий

```bash
preflight_check_versions() {
    # ffmpeg >= 6.0
    local ffver=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}' | cut -d. -f1)
    if [[ "$ffver" -lt 6 ]]; then
        echo "[videomaker] ffmpeg $ffver: требуется 6.0+"
        exit 1
    fi
    
    # node >= 20
    local nodever=$(node -v | sed 's/v//' | cut -d. -f1)
    if [[ "$nodever" -lt 20 ]]; then
        echo "[videomaker] node $nodever: требуется 20+"
        exit 1
    fi
    
    # uv (любая актуальная)
    # pnpm (любая актуальная)
}
```

### 58.3 Установка зависимостей приложения

```bash
preflight_install_deps() {
    echo "[videomaker] uv sync..."
    (cd apps/backend && uv sync)
    
    echo "[videomaker] pnpm install..."
    (cd apps/frontend && pnpm install --frozen-lockfile)
}
```

### 58.4 Health-check opportunities

```bash
preflight_health() {
    # VideoToolbox available?
    if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q hevc_videotoolbox; then
        echo "[videomaker] VideoToolbox HEVC: ✓"
    else
        echo "[videomaker] VideoToolbox HEVC: ✗ (fallback на libx265)"
    fi
    
    # .env присутствует?
    if [[ ! -f .env ]]; then
        echo "[videomaker] .env отсутствует — копирую из .env.example"
        cp .env.example .env
        echo "[videomaker] ⚠️  отредактируй .env (GEMINI_API_KEY обязателен)"
    fi
}
```

### 58.5 Flag для skip

- `--skip-install` — не запускать uv sync / pnpm install (если пользователь знает, что deps актуальны).
- `--skip-health` — не проверять VideoToolbox.

### 58.6 Verification

- [ ] На чистой системе без `uv` — подсказка ставится.
- [ ] С `uv` но без `.env` — копируется.
- [ ] С правильным env — запуск идёт дальше.

### 58.7 Commit + Serena

---

## GATE-чекпоинт

- [ ] `./run.sh` на системе без зависимостей — подсказывает установку, выходит с 1.
- [ ] На готовой системе — проходит preflight за <5 с.
- [ ] Install-этап идемпотентен (повторный вызов не ломает).
- [ ] VideoToolbox проверен в health.

---

## Артефакт на выходе

Обновлённый `run.sh` с preflight-секциями.
