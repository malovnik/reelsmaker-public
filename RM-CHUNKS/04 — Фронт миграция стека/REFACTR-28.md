# REFACTR-28 — Миграция роутинга (projects, jobs, settings)

> **Этап:** 04
> **Шаг:** 29 из 67
> **Зависимости:** REFACTR-27 (Vite-заготовка), REFACTR-01 (карта маршрутов).
> **Следующий шаг:** REFACTR-29 (API-клиент + TanStack Query)

---

## Роли

### R-FRONTEND-ARCHITECT
**Soul:** Роутинг — скелет приложения. Делаем его верно с первого раза, всё остальное встанет на место.

---

## ТРИЗ-принцип

*Принцип матрёшки.* TanStack Router file-based = иерархическая структура файлов = иерархия роутов. Следуем её конвенциям, не изобретаем свои.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 28.1 Перечень маршрутов (из REFACTR-01)

19 маршрутов → преобразование в TanStack структуру:

```
src/routes/
    __root.tsx
    index.tsx                           →  /
    projects/
        index.tsx                        →  /projects
    jobs/
        $jobId/
            index.tsx                    →  /jobs/{id}
            tinder.tsx                   →  /jobs/{id}/tinder
            reels/
                $reelId.tsx              →  /jobs/{id}/reels/{reelId}
    settings/
        layout.tsx
        brand.tsx                        →  /settings/brand
        models.tsx                       →  /settings/models
        connections.tsx                  →  /settings/connections
        prompts.tsx                      →  /settings/prompts
        subtitles.tsx                    →  /settings/subtitles
        profiles.tsx                     →  /settings/profiles
        performance.tsx                  →  /settings/performance
        post-production.tsx              →  /settings/post-production
    schedule/
        index.tsx                        →  /schedule
    scheduler/
        index.tsx                        →  /scheduler
        accounts/index.tsx               →  /scheduler/accounts
        new/index.tsx                    →  /scheduler/new
        presets/index.tsx                →  /scheduler/presets
        campaigns/
            $id.tsx                      →  /scheduler/campaigns/{id}
```

### 28.2 Сгенерировать файлы

Для каждого пути — создать файл через TanStack router CLI или вручную.

Каждый файл содержит:
```tsx
import { createFileRoute } from '@tanstack/react-router';
export const Route = createFileRoute('/path/here')({
  component: ComponentName,
});
function ComponentName() { return <div>TODO: migrate from Next.js</div>; }
```

`TODO: migrate from Next.js` — не нарушение запрета TODO/FIXME, так как это временный placeholder **внутри** этапа (будет заполнен в REFACTR-30 через перенос существующих компонентов). Перед GATE этапа 04 все такие плейсхолдеры будут заменены.

### 28.3 Нав между роутами

- [ ] Все `<Link href="/...">` из Next.js → `<Link to="/...">` TanStack.
- [ ] `useRouter().push(...)` → `useNavigate()({ to: ... })`.

### 28.4 Layout маршруты

- [ ] `__root.tsx` — AppShell (пока заглушка, полная версия — REFACTR-30).
- [ ] `settings/layout.tsx` — обёртка для всех settings-страниц.

### 28.5 Smoke

- [ ] Все 19 маршрутов открываются без 404.
- [ ] Каждый показывает placeholder.
- [ ] Девтулзы TanStack Router показывают дерево.

### 28.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] 19 файлов маршрутов созданы.
- [ ] TanStack Router devtools показывает полное дерево.
- [ ] Навигация работает (клик по Link → переход без перезагрузки).
- [ ] Нет console.error при открытии любого маршрута.

---

## Артефакт на выходе

Файловая структура `src/routes/` с 19 маршрутами.
