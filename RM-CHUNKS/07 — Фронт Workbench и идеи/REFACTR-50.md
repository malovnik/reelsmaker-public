# REFACTR-50 — Прогресс рендера + список клипов + экспорт

> **Этап:** 07
> **Шаг:** 51 из 67
> **Зависимости:** REFACTR-49 (approve UI), REFACTR-21..23 (render).
> **Следующий шаг:** REFACTR-51 (Settings IA)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Рендер — финал pipeline. Пользователь ждёт. Визуальный прогресс должен давать понимание: сколько ещё.

### R-UX-WRITER
**Soul:** «Готово 3 из 5» понятнее, чем «60%».

---

## ТРИЗ-принцип

*Принцип обратной связи.* Каждый этап рендера отслеживается отдельно (per-clip). Не один общий прогресс-бар.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 50.1 Триггер рендера

После approve идей — кнопка «Рендерить одобренные (N)» (где N — число approved).

`POST /api/projects/{pid}/render/start` → backend запускает рендер всех approved.

### 50.2 Таб «Клипы»

Layout:
- Шапка: общий прогресс + кнопка «Открыть папку в Finder».
- Grid клипов (aspect-ratio 9:16):
  - Каждый клип — карточка с thumbnail, названием идеи, статусом (rendering / ready / error), прогрессом.
  - Клик → preview в lightbox (video player).
  - Меню: download, open-in-Finder, удалить.

### 50.3 Общий прогресс

```
Готово 3 из 8                        ▓▓▓▓▓░░░░░  37%
   1 в рендере                       осталось ~5 мин
```

Оценка времени: backend возвращает `avg_time_per_clip` + `remaining_clips`.

### 50.4 Карточка клипа

- Thumbnail: первый кадр готового клипа или placeholder (рендер идёт).
- Верх: статус chip (rendering / ready / error).
- Центр: название идеи (text-md).
- Низ: длина клипа (0:18), размер (3.2 MB), дата.
- Hover: меню с download/open/delete.

### 50.5 Download

`GET /api/projects/{pid}/clips/{clip_id}/download` — backend отдаёт файл. Фронт: `<a href="..." download>`.

### 50.6 Export-all (zip)

Кнопка «Скачать все (zip)» — `GET /api/projects/{pid}/clips/download-all` → zip-архив.

### 50.7 SSE события рендера

- `render_clip_started {clip_id}` → статус → rendering.
- `render_clip_progress {clip_id, percent}` → обновление бара.
- `render_clip_done {clip_id, output_path, size}` → статус → ready.
- `render_all_done {count}` → toast «Готово 8 рилсов!».

### 50.8 Lightbox preview

Радикс Dialog в fullscreen-варианте:
- Video player по центру, max-size 80vh.
- Controls внизу: download, open-in-Finder.
- Prev/next стрелки для перехода между клипами.
- ESC — закрыть.

### 50.9 Verify frontend-design

- [ ] Aspect ratio 9:16 для клипов (вертикаль) — grid адаптирован.
- [ ] Accent — только на primary CTA и active states.
- [ ] Прогресс — читаем в любой момент.

### 50.10 Commit + Serena + лог

### 50.11 Итог Этапа 07

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 07 ЗАВЕРШЁН. Workbench готов.»

---

## GATE-чекпоинт

- [ ] Кнопка «Рендерить» запускает backend.
- [ ] SSE обновляет статусы клипов live.
- [ ] Grid клипов показывает thumbnail + статус + прогресс.
- [ ] Preview в lightbox.
- [ ] Download одиночного + all-zip работает.
- [ ] **Этап 07 ЗАВЕРШЁН.**

---

## Артефакт на выходе

ClipsTab + ClipCard + ClipLightbox + RenderProgressBar + download.
