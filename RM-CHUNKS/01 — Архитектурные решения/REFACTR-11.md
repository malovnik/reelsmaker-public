# REFACTR-11 — ADR: Темы (CSS variables + двухсторонний persist)

> **Этап:** 01
> **Шаг:** 12 из 67
> **Зависимости:** REFACTR-08 (storage).
> **Следующий шаг:** REFACTR-12 (Итоговая архитектурная диаграмма)

---

## Роли

### R-DESIGN-ALCHEMIST — Дизайн-алхимик
**Профессия:** Senior UI/UX designer-dev.
**Soul:** Тёмная тема ≠ «invert of light». Это отдельная палитра, со своим контрастом, своими spacing-ощущениями, своими иконками.

### R-ARCHITECT
**Soul:** Тема — глобальное состояние, но она не должна вызывать перерендер всего UI. CSS variables + класс на `<html>` — правильный путь.

---

## ТРИЗ-принцип

*Принцип копирования.* Дублировать палитру (dark + light), но держать одни и те же токены (`--bg-primary`, `--text-primary`, `--accent`). Переключение темы меняет только значения CSS-переменных, не структуру DOM.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 11.1 Модель темы

**Семантические токены (одинаковые для обеих тем):**
- `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`
- `--text-primary`, `--text-secondary`, `--text-muted`, `--text-on-accent`
- `--border-subtle`, `--border-default`, `--border-strong`
- `--accent-primary`, `--accent-hover`, `--accent-muted`
- `--success`, `--warning`, `--danger`, `--info`
- `--shadow-sm`, `--shadow-md`, `--shadow-lg`

**Два набора значений:**
- `html[data-theme="dark"]` — dark палитра (default).
- `html[data-theme="light"]` — light палитра.

### 11.2 Persist-стратегия

**Источник правды:** localStorage ключ `videomaker-theme` = `"dark" | "light" | "system"`.
**Синхронизация с бэком:** при изменении темы — PUT `/api/settings/device/theme`. При логине в новой вкладке — подтягиваем с бэка.

**Инициализация до гидрации:**
```html
<script>
  try {
    const t = localStorage.getItem('videomaker-theme') || 'dark';
    document.documentElement.dataset.theme = t === 'system'
      ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
  } catch {}
</script>
```
Встраивается в `index.html` до React-монтирования — избегает flash of wrong theme.

### 11.3 Переключатель

UI: `DropdownMenu` с 3 опциями: System / Dark / Light. Иконка в `TopBar`.

### 11.4 API на бэке

```
GET /api/settings/device       → { theme: "dark" | "light" | "system" }
PUT /api/settings/device       → { theme }
```

### 11.5 Написать ADR

`docs/adr/0005-theming.md` — создан (≈420 строк, MADR).

### 11.6 Serena memory

- [x] `write_memory(name="refactr-11-adr-theming", content="...")`.

---

## GATE-чекпоинт

- [x] ADR-0005 принят (status ACCEPTED).
- [x] Перечислены 24 семантических токена (Surface×4 + Paper×2 + Border×2 + Mute×2 + Accent×4 + Semantic×11 + Interactive×4 + Status×4 + Profile×5 + Shadow×4 + Radius×3). WCAG AA проверка задокументирована (все ≥Δ0.50 кроме `--danger` light — нужно L=0.48).
- [x] Persist двухсторонний описан: localStorage-first (`videomaker-theme`, 3 значения), async backend sync через `GET/PUT /api/settings/device`, conflict resolution «localStorage выигрывает», `storage` event для cross-tab, `matchMedia` для system-mode tracking.
- [x] Flash-prevention inline script (~400 bytes) в `<head>` до React-монтирования, try/catch с fallback на dark, `documentElement.dataset.theme` + `colorScheme` устанавливаются синхронно при parse-time.

---

## Артефакт на выходе

`docs/adr/0005-theming.md`.
