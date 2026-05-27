# REFACTR-29 — API-клиент + TanStack Query hooks + SSE

> **Этап:** 04
> **Шаг:** 30 из 67
> **Зависимости:** REFACTR-28 (роутинг), REFACTR-14..20 (backend endpoints).
> **Следующий шаг:** REFACTR-30 (Миграция shell)

---

## Роли

### R-FRONTEND-ARCHITECT
**Soul:** TanStack Query — источник правды для серверных данных. Всё что от сервера — через хуки `useQuery`/`useMutation`. Никаких руками прописанных fetch+useState.

### R-REALTIME-ENG (консультативно)
**Soul:** SSE — поток. Не запрос. Интегрируется как custom `useEventSource` хук + отправка инвалидации в QueryClient.

---

## ТРИЗ-принцип

*Принцип разделения.* Синхронные данные — через Query. Прогресс pipeline — через SSE. Не смешивать. SSE не кеширует, Query кеширует.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 29.1 Базовый fetcher

`src/lib/api.ts`:
- Функция `api<T>(path, init?): Promise<T>` — обёртка над fetch.
- Базовый URL — из env `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).
- JSON-сериализация/десериализация.
- Обработка If-Match для autosave (передача ETag).
- Автоматический error-throwing на !ok.

### 29.2 Query keys convention

`src/lib/queryKeys.ts`:

```ts
export const qk = {
  projects: () => ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  projectSettings: (id: string) => ['projects', id, 'settings'] as const,
  ideas: (projectId: string) => ['projects', projectId, 'ideas'] as const,
  jobs: () => ['jobs'] as const,
  job: (id: string) => ['jobs', id] as const,
  settings: {
    brand: () => ['settings', 'brand'] as const,
    models: () => ['settings', 'models'] as const,
    // ...
  },
};
```

### 29.3 Hooks

`src/features/projects/queries.ts`:

```ts
export const useProjects = () => useQuery({ queryKey: qk.projects(), queryFn: () => api<Project[]>('/api/projects') });
export const useProject = (id: string) => useQuery({ queryKey: qk.project(id), queryFn: () => api<Project>(`/api/projects/${id}`) });

export const useUpdateSettings = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (snapshot: ProjectSettingsSnapshot) => api(`/api/projects/${projectId}/settings`, {
      method: 'PUT',
      body: JSON.stringify(snapshot),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.project(projectId) }),
  });
};
```

Аналогично для:
- ideas (useIdeas, useApproveIdea, useRejectIdea, useRegenerateIdea).
- jobs (useJobs, useStartJob, useRestartFromStage).
- settings (useBrand, useModels, useConnections и т.п.).

### 29.4 SSE hook

`src/lib/useEventSource.ts`:

```ts
export function useEventSource(url: string | null, onEvent: (event: MessageEvent) => void) {
  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    es.onmessage = onEvent;
    es.onerror = () => { /* reconnect logic */ };
    return () => es.close();
  }, [url]);
}
```

Использование: `useEventSource(job ? `/api/jobs/${job.id}/events` : null, (e) => { ... queryClient.invalidateQueries... })`.

### 29.5 Optimistic updates

Для approve/reject идей — optimistic:

```ts
mutationFn: () => api(`/api/projects/${pid}/ideas/${id}/approve`, { method: 'POST' }),
onMutate: async () => {
  await qc.cancelQueries({ queryKey: qk.ideas(pid) });
  const prev = qc.getQueryData(qk.ideas(pid));
  qc.setQueryData(qk.ideas(pid), (old: Idea[] = []) => old.map(i => i.id === id ? { ...i, status: 'approved' } : i));
  return { prev };
},
onError: (_, __, ctx) => qc.setQueryData(qk.ideas(pid), ctx?.prev),
onSettled: () => qc.invalidateQueries({ queryKey: qk.ideas(pid) }),
```

### 29.6 Smoke

- [ ] `useProjects()` возвращает реальные данные (бэк запущен).
- [ ] `useUpdateSettings()` работает — изменения сохраняются.
- [ ] SSE на /jobs/:id передаёт events, Query инвалидируется.

### 29.7 Verify — нет прямых fetch

- [ ] `grep -r "fetch(" apps/frontend-vite/src` → 0 результатов, кроме `src/lib/api.ts`.

### 29.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] API-обёртка работает.
- [ ] Query keys convention применены.
- [ ] Минимум 10 Query hooks + 5 Mutation hooks.
- [ ] SSE hook работает на живом прогрессе.
- [ ] 0 прямых fetch вне `api.ts`.

---

## Артефакт на выходе

`src/lib/api.ts` + `src/lib/queryKeys.ts` + `src/lib/useEventSource.ts` + `src/features/**/queries.ts` по фичам.
