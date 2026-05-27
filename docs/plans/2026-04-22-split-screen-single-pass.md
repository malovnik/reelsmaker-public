# Single-Pass Split-Screen Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note:** Production-grade refactor, NOT feature development. NO new unit tests (project constraint). Each task = atomic changes + build gates + commit + push to `origin/feat/glm-provider`.

**Goal:** Переписать split-screen render с 3 последовательных ffmpeg passes на **один проход** с единым `-filter_complex`. Устранить bug двойной обработки fit/fill, сделать preview в SplitScreenPreviewEditor 100% соответствующим рендеру, сэкономить 2 disk-write + decode/encode pass.

**Architecture:** Использовать готовый `CompiledGraph.filter_complex` от существующей функции `build_filter_graph(graph)` как inner body chain, extend его split-screen фрагментом (vstack + subtitles overlay) и выполнить одним ffmpeg subprocess. Frontend добавляет inline warning что main fit/fill не применим в split-режиме.

**Tech Stack:** Python 3.12 backend (FastAPI, Pydantic v2, asyncio subprocess), TypeScript/React frontend (Next.js 16, shadcn/ui + Tailwind).

---

## Context — верифицированное состояние кода на 2026-04-22

### Ключевые backend компоненты

**`apps/backend/src/videomaker/services/filter_graph_builder.py:37-72`** — `CompiledGraph` dataclass:
- Поля: `inputs: list[Path]`, `filter_complex: str`, `output_video_label: str`, `output_audio_label: str`, `extra_args: list[str]`, `output_path: Path`, `diagnostics: dict`.
- Метод `to_argv(ffmpeg_path='ffmpeg') -> list[str]` собирает полную ffmpeg argv с `-y -hide_banner -nostdin -loglevel info -progress pipe:1`, все inputs, filter_complex, map'ы, extra_args, output_path.

**`apps/backend/src/videomaker/services/filter_graph_builder.py:75`** — `build_filter_graph(graph: ProjectGraph) -> CompiledGraph` — pure function. Собирает полный body filter_complex: Stage A per-cut trim → face crop / scale / fps → concat → Stage B zoom → Stage C extras → Stage D loudnorm → optional subtitle burn-in → optional intro/outro concat.

**`apps/backend/src/videomaker/services/split_screen.py`:**
- `_compute_panels(config)` — pure function, возвращает main и companion rects `(x, y, w, h)` в 1080×1920 canvas.
- `_scale_expression(width, height, mode)` — возвращает ffmpeg scale/pad/crop фильтр для fit/fill/manual режимов.
- `_escape_ass_path(path)` — экранирует путь для `subtitles=` filter.
- `build_filter_complex(config, *, subtitle_ass_path)` — legacy 2-input композитор (reel_mp4 + companion).
- `apply_split_screen(*, reel_path, companion_path, config, out_path, ...)` — legacy 2-input asyncio subprocess.

**`apps/backend/src/videomaker/services/pipeline_stages/render.py:1328-1510`** — `_render_and_persist_reels`. Вызывает `ProjectRenderer.render_many(graphs)` для body-рендера. В split branch (строки 1402-1469) применяет `apply_split_screen` (Pass 2) + `concat_with_intro_outro` (Pass 3).

**`apps/backend/src/videomaker/services/pipeline_stages/render.py:~576`** — вызов `build_project_graph(..., exclude_post_production=split_enabled, ...)` (точную строку субагент найдёт через Serena или grep).

### Frontend компоненты

**`apps/frontend/src/components/settings/post-production/SplitScreenSection.tsx`** — split-screen секция в settings. Получает `values.split_screen` и `update` callback.

**`apps/frontend/src/components/upload/UploadWizard.tsx`** — upload wizard. Имеет fit_mode select и per-job split-screen override.

---

## File Structure

Backend:
- `apps/backend/src/videomaker/services/split_screen.py` — добавить новую функцию `render_split_single_pass(...)`, переиспользующую `_compute_panels`, `_scale_expression`, `_escape_ass_path`. Существующие `apply_split_screen` + `build_filter_complex` остаются до Task 5.
- `apps/backend/src/videomaker/services/pipeline_stages/render.py` — заменить 3-pass chain в split branch одним вызовом single-pass функции. Изменить exclude-флаги в `build_project_graph` call.

Frontend:
- `SplitScreenSection.tsx` — inline warning banner вверху split controls.
- `UploadWizard.tsx` — hint под fit_mode select если split override активен.

Паттерн — multi-file сервисы (существующий), новой декомпозиции не делаем.

---

### Task 1: Deep research — изучить primitives для интеграции

**Files:**
- Read-only: `apps/backend/src/videomaker/services/filter_graph_builder.py`
- Read-only: `apps/backend/src/videomaker/services/project_renderer.py`
- Read-only: `apps/backend/src/videomaker/services/split_screen.py`

Задача — **понять контракт** `build_filter_graph` и `CompiledGraph` перед написанием integration code. Конкретно ответить на 3 вопроса:

1. Какими именно лейблами (`[v_main]`? `[v_out]`? другое) оканчивается `CompiledGraph.filter_complex` video стрим — это extension point для Task 2.
2. Включает ли `filter_complex` intro/outro concat когда `graph.intro_path`/`outro_path` не None — т.е. single-pass через `build_filter_graph` автоматически получит intro/outro без дополнительной работы.
3. Включает ли `filter_complex` subtitle burn-in когда `graph.subtitle_path` задан, и если да — какой порядок (субтитры до vstack или после) нам нужен в Task 2.

- [ ] **Step 1: Прочитать полный filter_graph_builder.py**

Команда:
```bash
cat <source-repo>/apps/backend/src/videomaker/services/filter_graph_builder.py
```

- [ ] **Step 2: Прочитать ProjectRenderer**

Команда:
```bash
sed -n '99,300p' <source-repo>/apps/backend/src/videomaker/services/project_renderer.py
```

Искать: как собирается ffmpeg subprocess, где progress-parsing (регекс по `out_time_ms=`), есть ли fallback на `-filter_complex_script` file при filter >100KB.

- [ ] **Step 3: Записать research memo в docstring модуля split_screen.py**

Файл: `apps/backend/src/videomaker/services/split_screen.py`

После существующего module docstring (строки 1-25), перед `from __future__ import annotations` — добавить module-level comment в стиле существующих заметок проекта:

```
# ─── Architecture note (2026-04-22 research) ──────────────────────────────
# Single-pass split-screen uses CompiledGraph.filter_complex (from
# build_filter_graph) as inner body chain. CompiledGraph:
#   - filter_complex: str ending with labels [output_video_label] / [output_audio_label]
#   - inputs: list[Path] (source + optional intro + optional outro)
# render_split_single_pass (below) extends filter_complex with:
#   - companion input at index len(inputs), via -stream_loop -1 at argv level
#   - vstack of [output_video_label] + scaled companion
#   - optional subtitles=ass overlay поверх full canvas
# ──────────────────────────────────────────────────────────────────────────
```

- [ ] **Step 4: Build gates**

```
cd apps/backend && uv run ruff check src/videomaker/services/split_screen.py
cd apps/backend && uv run pyright src/videomaker/services/split_screen.py
```
Expected: оба `All checks passed!` / `0 errors`.

- [ ] **Step 5: Commit**

```
git add apps/backend/src/videomaker/services/split_screen.py
git commit -m "docs(split_screen): architecture note for single-pass refactor"
git push origin feat/glm-provider
```

---

### Task 2: Реализовать render_split_single_pass

**Files:**
- Modify: `apps/backend/src/videomaker/services/split_screen.py` — добавить новую async функцию после `apply_split_screen`.

**Design contract** (docstring для функции):

```
async def render_split_single_pass(
    *,
    graph: ProjectGraph,
    companion_path: Path,
    split_config: SplitScreenConfig,
    subtitle_ass_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> None

Рендер рилса с split-screen одним ffmpeg вызовом.

В отличие от legacy-пары apply_split_screen + concat_with_intro_outro,
берёт RAW source через graph и в одном filter_complex делает: cuts →
face crop / scale → concat → loudnorm (всё через build_filter_graph) +
vstack с companion + subtitles + intro/outro (уже внутри compiled chain
если graph.intro_path / outro_path заданы).

Raises SplitScreenError если input не найден или ffmpeg упал.
```

- [ ] **Step 1: Добавить импорты**

В top-of-file импорты после существующих (`asyncio`, `Path`, `SplitScreenConfig`):

```
from videomaker.models.project_graph import ProjectGraph
from videomaker.services.filter_graph_builder import build_filter_graph
```

Верифицировать фактический путь пакета для `ProjectGraph` — если он в `videomaker.services.project_graph`, адаптировать.

- [ ] **Step 2: Реализовать функцию**

После существующей `apply_split_screen` (примерно строка 263) добавить `render_split_single_pass`. Алгоритм:

1. Валидация входов (companion_path.exists(), subtitle_ass_path.exists() если задан) — raise `SplitScreenError` если нет. Паттерн существующей `apply_split_screen`.
2. `compiled = build_filter_graph(graph)` — получить body chain.
3. `companion_input_idx = len(compiled.inputs)` — порядковый номер companion в argv (после source + intro + outro).
4. Рассчитать rects: `(mx, my, mw, mh), (cx, cy, cw, ch) = _compute_panels(split_config)`.
5. Рассчитать scale expressions: `main_scale = _scale_expression(mw, mh, split_config.main_fit_mode)`, аналогично для companion.
6. Построить `split_parts: list[str]`:
   - Black background: `color=c=black:s=1080x1920:d=1[split_bg]`
   - Main scale: `{compiled.output_video_label}{main_scale}[split_main]`
   - Companion: `[{companion_input_idx}:v]{comp_scale},setpts=PTS-STARTPTS[split_comp]`
   - Main overlay: `[split_bg][split_main]overlay=x={mx}:y={my}:shortest=0[split_with_main]`
   - Companion overlay + subtitles (conditional):
     - Без субтитров: `[split_with_main][split_comp]overlay=x={cx}:y={cy}:shortest=1[split_out_v]`
     - С субтитрами: `[split_with_main][split_comp]overlay=x={cx}:y={cy}:shortest=1[split_canvas]` + `[split_canvas]subtitles={escaped}[split_out_v]`
7. `full_filter_complex = compiled.filter_complex + ";" + ";".join(split_parts)`
8. Построить argv: по образцу `CompiledGraph.to_argv` — `ffmpeg_path, "-y", "-hide_banner", "-nostdin", "-loglevel", "warning", "-progress", "pipe:1"`, затем все `compiled.inputs` через `-i`, затем `-stream_loop -1 -i companion_path`, затем `-filter_complex full_filter_complex`, затем `-map [split_out_v] -map compiled.output_audio_label`, затем `compiled.extra_args`, затем `compiled.output_path`.
9. `log.info("split_screen.single_pass.start", ...)` со всеми параметрами (cuts count, intro/outro from graph, split mode, burn_subtitles flag, filter_chars count, out).
10. Запустить subprocess (паттерн точно такой же как в `apply_split_screen`, строки 244-262 — `asyncio.create_subprocess_exec` + `communicate()` + проверка returncode).
11. При ненулевом returncode — raise `SplitScreenError(f"single-pass split-screen failed (code {rc}): {stderr_text[:500]}")`.
12. `log.info("split_screen.single_pass.done", out=..., returncode=rc)`.

Важно: НЕ переиспользовать `compiled.to_argv()` напрямую — он не знает про companion input и не переключает map на `[split_out_v]`. Строить argv руками, следуя паттерну `to_argv`.

- [ ] **Step 3: Build gates**

```
cd apps/backend && uv run ruff check src/videomaker/services/split_screen.py
cd apps/backend && uv run pyright src/videomaker/services/split_screen.py
```
Expected: `All checks passed!` / `0 errors`.

- [ ] **Step 4: Commit**

```
git add apps/backend/src/videomaker/services/split_screen.py
git commit -m "feat(split_screen): render_split_single_pass one-call architecture

Использует build_filter_graph(graph) как body chain, extends
filter_complex split vstack + subtitles overlay. Один ffmpeg
subprocess вместо body→apply_split→concat chain.

Функция добавлена но не вызывается — wiring в render.py
в Task 3."
git push origin feat/glm-provider
```

---

### Task 3: Интеграция single-pass в render.py split branch

**Files:**
- Modify: `apps/backend/src/videomaker/services/pipeline_stages/render.py` — split branch в `_render_and_persist_reels` (~строки 1402-1469), import split_screen module.

- [ ] **Step 1: Найти вызов build_project_graph с exclude flags**

Subagent использует Serena: `mcp__serena__search_for_pattern("exclude_post_production=split_enabled")` в файле `apps/backend/src/videomaker/services/pipeline_stages/render.py`. Должно найтись на строке ~576.

Также grep'нуть `exclude_post_production\|exclude_subtitles` по всему проекту чтобы убедиться что эти флаги не зависят от split_enabled нигде ещё.

- [ ] **Step 2: Изменить exclude flags → False**

В найденном вызове `build_project_graph(...)` изменить `exclude_post_production=split_enabled` → `exclude_post_production=False`. Если есть `exclude_subtitles=split_enabled` — тоже `False`. Комментарий рядом обновить: "с single-pass architecture 2026-04-22 весь контекст intro/outro/subs встроен в graph → filter_complex от build_filter_graph. Split branch extends его vstack+subtitles на top."

- [ ] **Step 3: Обновить импорт**

Найти в `render.py` импорт:
```
from videomaker.services.split_screen import (
    SplitScreenError,
    apply_split_screen,
)
```

Изменить на:
```
from videomaker.services.split_screen import (
    SplitScreenError,
    apply_split_screen,
    render_split_single_pass,
)
```

(`apply_split_screen` остаётся в импорте — удаление в Task 5 conditionally.)

- [ ] **Step 4: Заменить split branch на single-pass вызов**

Локация: `apps/backend/src/videomaker/services/pipeline_stages/render.py` строки 1402-1469 (блок `if split_enabled:` внутри цикла `for graph, result in zip(...)`).

Заменить ВСЁ содержимое этого if-блока (от `assert post_production_config is not None` до `continue` после `ConcatError`) на:

```python
        if split_enabled:
            assert post_production_config is not None
            assert post_production_config.split_screen.companion_path is not None

            companion_path = Path(post_production_config.split_screen.companion_path)
            sub_path_for_split = subtitle_paths_by_reel.get(graph.reel_id)
            subtitle_ass_path = (
                sub_path_for_split
                if sub_path_for_split is not None and sub_path_for_split.exists()
                else None
            )
            try:
                # Single-pass (2026-04-22): один ffmpeg из source → final.
                # Переписывает result.output_path новым контентом.
                await render_split_single_pass(
                    graph=graph,
                    companion_path=companion_path,
                    split_config=post_production_config.split_screen,
                    subtitle_ass_path=subtitle_ass_path,
                )
                reel_mp4 = Path(result.output_path)
                result.file_size_bytes = reel_mp4.stat().st_size
                log.info(
                    "split_screen_single_pass_applied",
                    job_id=job_id,
                    reel_id=graph.reel_id,
                    new_size=result.file_size_bytes,
                    has_intro=graph.intro_path is not None,
                    has_outro=graph.outro_path is not None,
                )
            except SplitScreenError as err:
                log.error(
                    "split_screen_failed",
                    job_id=job_id,
                    reel_id=graph.reel_id,
                    error=str(err),
                )
                continue
```

Исчезает импорт/вызов `concat_with_intro_outro` и `ConcatError` — они больше не нужны в split branch. Проверить что `ConcatError` ещё используется где-то в `render.py` (вероятно в non-split branch если есть) — если нет, удалить из импорта. Если да, оставить.

- [ ] **Step 5: Build gates**

```
cd apps/backend && uv run ruff check src/videomaker/services/pipeline_stages/render.py
cd apps/backend && uv run pyright src/videomaker/services/pipeline_stages/render.py
```
Expected: `All checks passed!` / `0 errors`.

- [ ] **Step 6: Commit**

```
git add apps/backend/src/videomaker/services/pipeline_stages/render.py
git commit -m "fix(render): wire split-screen single-pass

Split branch в _render_and_persist_reels вызывает
render_split_single_pass — один ffmpeg вместо
apply_split_screen+concat_with_intro_outro.

build_project_graph для split теперь с
exclude_post_production=False: весь контекст
(intro/outro/subs) встроен в filter_complex.

Fixes двойная обработка fit/fill: ранее основной
target_aspect применялся в ProjectRenderer body →
apply_split_screen на результат. Теперь body проходит
один раз через build_filter_graph, split transforms
поверх. Preview в кабинете 1:1 соответствует рендеру."
git push origin feat/glm-provider
```

---

### Task 4: Frontend — inline warning в split-режиме

**Files:**
- Modify: `apps/frontend/src/components/settings/post-production/SplitScreenSection.tsx`
- Modify: `apps/frontend/src/components/upload/UploadWizard.tsx`

- [ ] **Step 1: SplitScreenSection warning banner**

Прочитать файл: `cat apps/frontend/src/components/settings/post-production/SplitScreenSection.tsx`

Найти самый внешний conditional rendering split controls (паттерн `{values.split_screen.enabled && (<...>)}` или аналогичный). В самом начале этого блока, ДО первого SliderRow/SelectRow, добавить warning banner:

```tsx
        <div className="rounded-md border border-amber-300/30 bg-amber-950/20 p-3 text-sm text-amber-200/90">
          <div className="font-medium mb-1">Split-режим активен</div>
          <div>
            Основные настройки <span className="font-mono">fit / fill</span> из
            глобальных не применяются к split-рилсам — кропом управляют{" "}
            <span className="font-mono">Main Panel Transform</span> и{" "}
            <span className="font-mono">Companion Panel Transform</span> ниже.
            Превью в этом разделе 1:1 соответствует финальному рендеру.
          </div>
        </div>
```

Если в проекте уже есть shadcn `<Alert>` компонент (Grep `@/components/ui/alert`) — предпочесть его вместо div. Тогда импорт `import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"` и:

```tsx
        <Alert variant="default" className="border-amber-300/30 bg-amber-950/20">
          <AlertTitle>Split-режим активен</AlertTitle>
          <AlertDescription>...</AlertDescription>
        </Alert>
```

- [ ] **Step 2: UploadWizard inline hint**

Прочитать файл: `cat apps/frontend/src/components/upload/UploadWizard.tsx`

Найти fit_mode select (поиск `fit_mode` или `Fit` в JSX). Определить state var хранящий split override (из useWizardState). Рядом с fit_mode (ниже) добавить conditional:

```tsx
        {splitScreenEnabled && (
          <p className="text-xs text-amber-300/80 mt-1">
            ⚠ В split-режиме этот параметр не применяется. Настройте кроп через
            Split-Screen Preview в post-production.
          </p>
        )}
```

Имя переменной `splitScreenEnabled` субагент заменит на фактическое из useWizardState.

- [ ] **Step 3: Build gates (frontend)**

```
cd <source-repo> && npx -p typescript tsc --noEmit -p apps/frontend/tsconfig.json
cd <source-repo> && pnpm -C apps/frontend build
```
Expected: tsc silent exit, pnpm `✓ Compiled successfully` + static pages generation complete.

- [ ] **Step 4: Commit**

```
git add apps/frontend/src/components/settings/post-production/SplitScreenSection.tsx apps/frontend/src/components/upload/UploadWizard.tsx
git commit -m "feat(ui): split-mode warning — main fit/fill не применяется

SplitScreenSection: amber warning banner вверху split
controls — уведомляет юзера что main fit/fill не
используется в split-режиме, кроп идёт через Panel
Transforms.

UploadWizard: inline hint под fit_mode select когда
per-job split override включён.

Соответствует backend-поведению после Task 3."
git push origin feat/glm-provider
```

---

### Task 5: Cleanup legacy (conditional)

**Files:**
- Potentially modify: `apps/backend/src/videomaker/services/split_screen.py` (удалить `apply_split_screen` + `build_filter_complex` если unused)
- Potentially modify: `apps/backend/src/videomaker/services/pipeline_stages/render.py` (убрать импорт `apply_split_screen`)

- [ ] **Step 1: Grep всех callers**

```
grep -rn "apply_split_screen" <source-repo>/apps/backend --include="*.py"
grep -rn "build_filter_complex" <source-repo>/apps/backend --include="*.py"
```

Ожидание после Task 3:
- `apply_split_screen` — только в import render.py (legacy, не вызывается), self-reference в docstring split_screen.py, определение в split_screen.py.
- `build_filter_complex` — только в split_screen.py (определение + вызов внутри apply_split_screen).

- [ ] **Step 2: Решение ветки**

- **Если `apply_split_screen` грепается только в 3 местах (import render.py + self-reference docstring + определение)** → УДАЛИТЬ.
- **Если есть другие callers** (например CLI / tests / other pipeline) → ОСТАВИТЬ с deprecated docstring.

- [ ] **Step 3a: Если УДАЛИТЬ**

В `pipeline_stages/render.py` убрать `apply_split_screen` из импорта:
```
from videomaker.services.split_screen import (
    SplitScreenError,
    render_split_single_pass,
)
```

В `split_screen.py` использовать Serena:
```
mcp__serena__safe_delete_symbol(name_path="apply_split_screen", ...)
mcp__serena__safe_delete_symbol(name_path="build_filter_complex", ...)
```

- [ ] **Step 3b: Если ОСТАВИТЬ с deprecated**

В `split_screen.py` в docstring `apply_split_screen` первой строкой добавить:
```
.. deprecated:: 2026-04-22
    Single-pass render_split_single_pass покрывает все production use cases.
    Эта функция оставлена для backward compat / CLI / tests.
```

- [ ] **Step 4: Build gates**

```
cd apps/backend && uv run ruff check src/videomaker/services/split_screen.py src/videomaker/services/pipeline_stages/render.py
cd apps/backend && uv run pyright src/videomaker/services/split_screen.py src/videomaker/services/pipeline_stages/render.py
```
Expected: `All checks passed!` / `0 errors`.

- [ ] **Step 5: Commit**

Если удаление применено:
```
git add apps/backend/src/videomaker/services/split_screen.py apps/backend/src/videomaker/services/pipeline_stages/render.py
git commit -m "chore(split_screen): remove legacy apply_split_screen + build_filter_complex

Заменено single-pass архитектурой (Task 3). Grep confirms
no other callers вне render.py split branch."
git push origin feat/glm-provider
```

Если deprecated-only:
```
git add apps/backend/src/videomaker/services/split_screen.py
git commit -m "docs(split_screen): mark apply_split_screen as deprecated

Single-pass render_split_single_pass покрывает production.
Legacy оставлен для backward compat."
git push origin feat/glm-provider
```

---

## Self-Review

**1. Spec coverage:**
- 3-pass → single-pass (Task 2 новая функция + Task 3 wiring) ✓
- Fix bug двойного fit/fill (Task 3 — exclude_post_production=False + build_filter_graph берёт RAW source) ✓
- UI warning (Task 4) ✓
- Cleanup legacy (Task 5) ✓
- Research deep (Task 1 — необходимо, ProjectGraph + CompiledGraph имеют нюансы которые subagent должен понять) ✓

Нет gap.

**2. Placeholder scan:**
- Task 2 Step 1: путь импорта `ProjectGraph` написан условно — subagent адаптирует (`models.project_graph` или `services.project_graph`). Explicit verification instruction, не placeholder.
- Task 3 Step 1: точная строка `exclude_post_production=split_enabled` — subagent находит через Serena/grep. Explicit method, не placeholder.
- Task 4 Step 2: имя state var `splitScreenEnabled` — написано что subagent подставит фактическое. Legitimate.
- Task 5: условные ветки с явным разрешением — legitimate.

Нет "TBD" / "add error handling" без кода.

**3. Type consistency:**
- `render_split_single_pass` signature (graph, companion_path, split_config, subtitle_ass_path, ffmpeg_path) идентичен в Task 2 и Task 3 call site.
- Labels filter_complex (`[split_bg]`, `[split_main]`, `[split_comp]`, `[split_with_main]`, `[split_canvas]`, `[split_out_v]`) консистентны в Task 2 Step 2.
- Pyright проверит фактические field имена `CompiledGraph.output_video_label` etc в build gate.

Консистентно.

---

**Plan complete and saved to `<source-repo>/docs/plans/2026-04-22-split-screen-single-pass.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task + two-stage review via `superpowers:subagent-driven-development`.

**2. Inline Execution** — tasks в current session через `superpowers:executing-plans`.

User сказал «гоу через субагентов» → идём в Subagent-Driven.
