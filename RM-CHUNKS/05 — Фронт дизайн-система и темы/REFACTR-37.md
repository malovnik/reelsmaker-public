# REFACTR-37 — ThemeProvider + persist + переключатель

> **Этап:** 05
> **Шаг:** 38 из 67
> **Зависимости:** REFACTR-11 (ADR theming), REFACTR-33 (палитры).
> **Следующий шаг:** REFACTR-38 (Motion)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-FRONTEND-ARCHITECT
**Soul:** Тема — глобальное состояние, но не через React Context. CSS переменные на `<html>` — быстрее (zero re-render), проще (0 пропов).

### R-A11Y-ENG
**Soul:** Respect system preference. При `system` — слушать `prefers-color-scheme` change.

---

## ТРИЗ-принцип

*Принцип копирования.* Тема = атрибут на `<html>`. CSS variables сами подстраиваются. React лишь даёт UI для переключения.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 37.1 Flash prevention script

`index.html` — inline script до монтирования React:

```html
<script>
  (function() {
    try {
      var t = localStorage.getItem('videomaker-theme') || 'dark';
      var resolved = t === 'system'
        ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : t;
      document.documentElement.dataset.theme = resolved;
    } catch (e) {
      document.documentElement.dataset.theme = 'dark';
    }
  })();
</script>
```

### 37.2 ThemeProvider

`src/design/ThemeProvider.tsx`:

```tsx
type Theme = 'dark' | 'light' | 'system';

interface ThemeContext {
  theme: Theme;
  resolvedTheme: 'dark' | 'light';
  setTheme: (t: Theme) => void;
}

const ctx = createContext<ThemeContext | null>(null);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState<Theme>(() =>
    (localStorage.getItem('videomaker-theme') as Theme) ?? 'dark'
  );
  const [resolvedTheme, setResolved] = useState<'dark' | 'light'>(() =>
    document.documentElement.dataset.theme as 'dark' | 'light'
  );

  // Listen to system preference
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const update = () => {
      const r = mq.matches ? 'dark' : 'light';
      setResolved(r);
      document.documentElement.dataset.theme = r;
    };
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [theme]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem('videomaker-theme', t);
    const r = t === 'system'
      ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
    setResolved(r);
    document.documentElement.dataset.theme = r;
    // Sync to backend (fire-and-forget)
    fetch('/api/settings/device', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: t }),
    }).catch(() => {});
  };

  return <ctx.Provider value={{ theme, resolvedTheme, setTheme }}>{children}</ctx.Provider>;
}

export const useTheme = () => {
  const c = useContext(ctx);
  if (!c) throw new Error('useTheme outside ThemeProvider');
  return c;
};
```

### 37.3 Backend sync

- На старте приложения: GET `/api/settings/device` → если `theme` отличается от localStorage → использовать backend-значение (приоритет).
- При изменении: PUT.

### 37.4 Переключатель

`src/design/components/ThemeSwitcher.tsx`:
- Radix DropdownMenu с 3 опциями: System / Dark / Light.
- Иконка: Moon/Sun/Monitor (из lucide).
- Активная опция — checked.

### 37.5 Размещение

- [ ] Вставить ThemeSwitcher в TopBar.
- [ ] Вставить ThemeProvider обёрткой в `main.tsx` (после QueryProvider).

### 37.6 Smoke

- [ ] Переключить на Light — страница мгновенно меняется, нет flash.
- [ ] Перезагрузить — тема сохранена.
- [ ] Открыть в другой вкладке — тоже dark (localStorage shared).
- [ ] Открыть DevTools → Application → Local Storage — видна запись `videomaker-theme`.
- [ ] Backend endpoint возвращает тему.

### 37.7 Commit + Serena

---

## GATE-чекпоинт

- [ ] Flash prevention работает (визуально проверено).
- [ ] Переключатель в TopBar.
- [ ] Persist localStorage + backend sync.
- [ ] System theme реагирует на ОС-preference.
- [ ] Нет re-render лавины при смене темы (проверено через React Profiler).

---

## Артефакт на выходе

ThemeProvider + ThemeSwitcher + flash prevention + backend sync.
