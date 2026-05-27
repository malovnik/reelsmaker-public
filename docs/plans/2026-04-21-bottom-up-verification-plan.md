# Bottom-Up Pipeline Runtime Verification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** независимо подтвердить или опровергнуть утверждение memory `videomaker-pipeline-reanimation-2026-04-21` о том, что pipeline bottom_up на ветке `feat/glm-provider` (HEAD после commits fb91668/d8202c3/61d0759/e5a45df) выдаёт 10 рилсов end-to-end на коротком видео. Получить stage-by-stage диагноз и, при деградации, локализовать root cause до конкретного файла/функции.

**Architecture:** это verification plan, не feature implementation. Каждая задача — атомарный диагностический шаг (запуск команды → сбор артефакта → сверка с критерием). Ветвление «если артефакт соответствует ожиданию → следующая задача; если нет → записать deviation и пойти по диагностической ветке Task 7».

**Tech Stack:** uv (Python 3.12) + FastAPI backend, Next.js 16 + pnpm frontend, SQLite для jobs, ffmpeg для render, Gemini для LLM, mlx-whisper для STT. Запуск — `./run.sh` из корня проекта.

**Working directory:** `<source-repo>` (все относительные пути относительно корня проекта).

---

## Evidence inventory (pre-task findings)

До начала плана зафиксированы два ключевых расхождения memory с реальностью, которые агент-исполнитель должен подтвердить перед запуском:

1. **Job `70ba41eb-f22a-45a6-b897-4a3fbbb12b87` упоминается в memory как «финальный smoke с 10/10 reels», но директории `data/artifacts/70ba41eb-f22a-45a6-b897-4a3fbbb12b87/` физически НЕТ.** В `data/artifacts/` существуют 11 других job'ов: `03ca98ea`, `18721422`, `40264fb1`, `8973caea`, `b21b73cf`, `b6809dc1`, `caa1fa63`, `cf3695e1`, `da070ab7`, `e1b081f2`, `ee2bf3b3`. Среди них `18721422` содержит `r32.mp4, r26.mp4, r27.mp4, r33.mp4` (нестандартная нумерация), `8973caea` — 5 reels (`reel_001..reel_005`).

2. **Memory утверждает о дампах `canvas_full.json`, `extraction_full.json`, `story_script.json`. Реальная структура любой существующей job-директории: `audio/ logs/ reels/ source/ subs/ text/` — JSON-дампов НЕ видно на top-level.** Они могут быть внутри `logs/` или `text/`, либо не писаться вовсе. Task 4 явно проверяет этот факт.

Эти два observation'а — отправная точка плана. Первая цель: воспроизвести smoke свежим прогоном и сверить с memory, не полагаясь на «10/10 в 70ba41eb».

---

## File structure

Этот план ТОЛЬКО читает код и запускает процессы. Код НЕ модифицируется в рамках verification. Любой fix локализуется в Task 7 и выносится в **отдельный** implementation plan `docs/plans/2026-04-21-bottom-up-fix-<stage>.md`, написанный после диагноза.

Артефакты самого verification-прогона:

- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/evidence-inventory.md` — финальный отчёт stage-by-stage
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/job-<new_job_id>/raw-logs.txt` — backend stderr/stdout во время прогона
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/job-<new_job_id>/sse-timeline.txt` — захваченный SSE поток
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/job-<new_job_id>/artifacts-tree.txt` — `find data/artifacts/<new_job_id>` output

Все эти файлы — диагностика, не код. Хранить в `docs/diagnostics/` чтобы не перемешивать с планами.

---

## Task 0: Branch + environment preconditions

**Files:**
- Read: `.env.example`
- Read (check exists): `.env`
- Read: `apps/backend/src/videomaker/models/runtime_settings.py`

- [ ] **Step 0.1: Verify git state**

Run:
```bash
cd <source-repo>
git branch --show-current
git log --oneline -5
git status --short
```

Expected: branch `feat/glm-provider`, HEAD на `31572ea docs(plan): ultraplan for three-pipeline restoration` (или новее после этого плана), working tree clean. Если есть uncommitted changes — **STOP**, записать `evidence-inventory.md` с git status и спросить пользователя.

- [ ] **Step 0.2: Check reanimation commits in history**

Run:
```bash
git log --oneline fb91668 d8202c3 61d0759 e5a45df 2>&1 | head -10
```

Expected: 4 строки с commits без ошибок. Это подтверждает что «реанимация» действительно существует в истории — memory не ссылается на несуществующие SHA.

Если любой commit не найден — **STOP**, зафиксировать в `evidence-inventory.md`: «memory references non-existent commit `<sha>`».

- [ ] **Step 0.3: Verify .env contains GEMINI_API_KEY**

Run:
```bash
test -f .env && grep -E '^GEMINI_API_KEY=.+' .env >/dev/null && echo "OK" || echo "MISSING"
```

Expected: `OK`. Если `MISSING` — **STOP**, попросить пользователя добавить `GEMINI_API_KEY` в `.env`. Без ключа pipeline упадёт на первом LLM-вызове и диагноз будет ложно-отрицательным.

- [ ] **Step 0.4: Verify narrative_mode default is bottom_up**

Run:
```bash
grep -n 'narrative_mode' apps/backend/src/videomaker/models/runtime_settings.py
```

Expected: строка вида `narrative_mode: NarrativeMode = "bottom_up"` (default = bottom_up). Если default другой — зафиксировать в `evidence-inventory.md` и явно переключить через API в Task 3.

- [ ] **Step 0.5: Check dependencies installed**

Run:
```bash
command -v uv && command -v pnpm && command -v ffmpeg && ffmpeg -version | head -1
```

Expected: три пути + `ffmpeg version 7.x` или выше. Если что-то отсутствует — установить per `README.md` («Требования»).

- [ ] **Step 0.6: Commit evidence**

Create `docs/diagnostics/2026-04-21-bottom-up-verification/` directory. Start `evidence-inventory.md` with sections:

```markdown
# Bottom-Up Verification — Evidence Inventory

## Pre-task findings
- Job 70ba41eb missing from data/artifacts/: [confirmed/refuted]
- JSON dumps canvas_full/extraction_full/story_script: [found in logs/.../<path> | not found anywhere]

## Task 0 results
- Branch: <output of git branch>
- HEAD: <output of git log -1>
- Reanimation commits: <all 4 present | missing: ...>
- GEMINI_API_KEY: [OK | MISSING]
- narrative_mode default: bottom_up (verified in runtime_settings.py:<line>)
- Tools: uv/<version>, pnpm/<version>, ffmpeg/<version>
```

Commit:
```bash
git add docs/diagnostics/2026-04-21-bottom-up-verification/
git commit -m "docs(diagnostics): task 0 environment preconditions for bottom-up verification"
```

---

## Task 1: Select test video

**Files:**
- Read: existing `data/uploads/*/source/*.mp4` file listing
- Ask user if no suitable test video found

- [ ] **Step 1.1: List candidates with duration**

Run:
```bash
for d in data/uploads/*/source/; do
  video=$(ls "$d"*.mp4 2>/dev/null | head -1)
  if [[ -n "$video" ]]; then
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$video" 2>/dev/null)
    size=$(du -h "$video" | cut -f1)
    echo "$video | dur=${dur}s size=${size}"
  fi
done | sort -t= -k2 -n
```

Expected: отсортированный список всех загруженных видео с их длительностью и размером. Цель verification — самое короткое видео, чтобы прогон занял ≤ 10 минут.

- [ ] **Step 1.2: Pick shortest video ≥ 60 sec ≤ 900 sec**

Из списка в 1.1 выбрать видео с `60 ≤ dur ≤ 900`. Memory утверждает что реанимация прошла на 11-мин (~660 сек), поэтому целимся в тот же диапазон.

Записать абсолютный путь в переменную shell:
```bash
TEST_VIDEO="<absolute_path_from_1.1>"
echo "Selected: $TEST_VIDEO ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TEST_VIDEO")s)"
```

- [ ] **Step 1.3: If no suitable candidate — ask user**

Если ни одно существующее видео не подходит (все > 900 сек или < 60 сек, или `data/uploads/` пуст):

```bash
echo "STOP: no suitable test video found."
echo "Please provide absolute path to a 60-900 sec video via chat."
```

Остановиться и запросить путь у пользователя. НЕ пытаться нарезать/сконвертировать существующее видео — это мутирует источник.

- [ ] **Step 1.4: Record selection in evidence-inventory.md**

Дописать в `evidence-inventory.md`:
```markdown
## Task 1: Test video
- Path: <TEST_VIDEO>
- Duration: <X>s
- Size: <Y>M
- Selection reason: shortest uploaded in valid range
```

---

## Task 2: Start dev environment + capture health

**Files:**
- Read: `run.sh`
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/backend-startup.log`

- [ ] **Step 2.1: Start run.sh in background with log capture**

Run:
```bash
cd <source-repo>
mkdir -p docs/diagnostics/2026-04-21-bottom-up-verification
./run.sh > docs/diagnostics/2026-04-21-bottom-up-verification/backend-startup.log 2>&1 &
RUN_PID=$!
echo "run.sh PID: $RUN_PID"
```

Expected: скрипт запущен в фоне. PID нужен для cleanup в Task 5.6.

- [ ] **Step 2.2: Wait for backend health**

Run:
```bash
for i in {1..60}; do
  if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    echo "Backend ready after ${i}s"
    break
  fi
  sleep 1
done
```

Expected: `Backend ready after Ns` где N ≤ 60. Если цикл завершился без успешного health — прочитать `backend-startup.log` для ошибок импорта/миграций.

Если `ModuleNotFoundError` — запустить `cd apps/backend && uv sync && cd -`, повторить Step 2.1.

Если `sqlalchemy.exc.OperationalError: no such table` — запустить `cd apps/backend && uv run alembic upgrade head && cd -`, повторить Step 2.1.

- [ ] **Step 2.3: Verify frontend ready**

Run:
```bash
for i in {1..60}; do
  if curl -sf http://localhost:3000 >/dev/null 2>&1; then
    echo "Frontend ready after ${i}s"
    break
  fi
  sleep 1
done
```

Expected: `Frontend ready after Ns`. Первый запуск `pnpm dev` занимает до 60 сек из-за Next.js compile.

- [ ] **Step 2.4: Verify current performance settings**

Run:
```bash
curl -s http://127.0.0.1:8000/api/v1/settings/performance | python3 -m json.tool > docs/diagnostics/2026-04-21-bottom-up-verification/pre-run-performance.json
cat docs/diagnostics/2026-04-21-bottom-up-verification/pre-run-performance.json
```

Expected: JSON c полем `"narrative_mode": "bottom_up"`. Если другое — **explicit PUT** на endpoint чтобы переключить:

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/settings/performance \
  -H 'Content-Type: application/json' \
  -d '{"narrative_mode": "bottom_up"}' | python3 -m json.tool
```

Дописать в `evidence-inventory.md`:
```markdown
## Task 2: Environment
- Backend started: OK (<N>s)
- Frontend started: OK (<M>s)
- narrative_mode at start: <bottom_up | other-and-switched>
```

---

## Task 3: Run job via API + capture SSE stream

**Files:**
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/job-<NEW_ID>/sse-timeline.txt`
- Reference: existing `apps/backend/src/videomaker/api/routes/jobs.py` for endpoints

- [ ] **Step 3.1: Inspect job upload endpoint**

Run:
```bash
grep -n 'router\.\(post\|get\)' apps/backend/src/videomaker/api/routes/jobs.py | head -20
```

Expected: список endpoints вида `POST /api/v1/jobs`, `GET /api/v1/jobs/{id}/stream`. Если endpoint'ы другие — скорректировать команды ниже по актуальным путям.

- [ ] **Step 3.2: POST job with test video**

Run:
```bash
JOB_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/v1/jobs \
  -F "file=@${TEST_VIDEO}" \
  -F 'narrative_mode=bottom_up')
echo "$JOB_RESPONSE" | python3 -m json.tool
NEW_JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
echo "NEW_JOB_ID=$NEW_JOB_ID"
mkdir -p docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}
```

Expected: JSON ответ с полями `id`, `status: "pending"|"ingest"|"running"`. `NEW_JOB_ID` — UUID.

Если endpoint возвращает 404 или 422 — прочитать FastAPI `/docs` на `http://127.0.0.1:8000/docs`, найти правильный endpoint и form-field name. Скорректировать `-F` flags.

- [ ] **Step 3.3: Capture SSE timeline**

Run:
```bash
timeout 1200 curl -sN http://127.0.0.1:8000/api/v1/jobs/${NEW_JOB_ID}/stream \
  > docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}/sse-timeline.txt &
SSE_PID=$!
```

Timeout 1200 сек = 20 мин (safety net для 11-мин видео с real-time factor 2-5x).

- [ ] **Step 3.4: Poll until job terminal state**

Run:
```bash
while true; do
  STATUS=$(curl -s http://127.0.0.1:8000/api/v1/jobs/${NEW_JOB_ID} | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
  echo "[$(date +%T)] status=$STATUS"
  case "$STATUS" in
    succeeded|failed|error|cancelled) break ;;
  esac
  sleep 10
done
echo "Final: $STATUS"
```

Expected: конечный статус за ≤ 20 мин. Если 20 мин прошло и не достигли terminal — убить curl и залогировать timeout:
```bash
kill $SSE_PID 2>/dev/null
echo "TIMEOUT" >> docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}/sse-timeline.txt
```

- [ ] **Step 3.5: Extract distinct SSE stages**

Run:
```bash
grep -oE '"stage":"[^"]+"' docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}/sse-timeline.txt | sort -u
```

Expected набор stages (из `README.md` pipeline flow): `ingest, transcribe, silence_cut, analyze, render`. Плюс под-stages analyze: `canvas, extraction, ranking, story_doctor, rhythm, variants, composer, closure_validator`.

Дописать в `evidence-inventory.md`:
```markdown
## Task 3: Job run
- NEW_JOB_ID: <uuid>
- Final status: <succeeded|failed|error|timeout>
- Total wall time: <N> min
- SSE stages observed: <sorted list>
- Missing SSE stages vs README expected: <delta>
```

Если final status `failed` или `error` — **STOP** Task 3 здесь, перейти сразу к Task 7 (диагностика) с information что pipeline упал на `<stage>`.

---

## Task 4: Collect + inventory all artifacts

**Files:**
- Create: `docs/diagnostics/2026-04-21-bottom-up-verification/job-<NEW_JOB_ID>/artifacts-tree.txt`

- [ ] **Step 4.1: Tree the artifact directory**

Run:
```bash
find data/artifacts/${NEW_JOB_ID} -type f -printf '%P\t%s\n' 2>/dev/null | sort \
  > docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}/artifacts-tree.txt
cat docs/diagnostics/2026-04-21-bottom-up-verification/job-${NEW_JOB_ID}/artifacts-tree.txt
```

Expected: non-empty листинг всех файлов с размерами. Если directory пустая или не существует — pipeline упал ДО записи артефактов, перейти к Task 7.

- [ ] **Step 4.2: Identify JSON dump locations**

Memory утверждает что следующие дампы создаются. Подтвердить реальное местоположение каждого:

```bash
for name in canvas_full.json extraction_full.json story_script.json reel_plan.json analysis_summary.json composer_candidates_breakdown.json; do
  found=$(find data/artifacts/${NEW_JOB_ID} -name "$name" 2>/dev/null)
  if [[ -n "$found" ]]; then
    echo "FOUND: $name -> $found ($(wc -c < "$found") bytes)"
  else
    echo "MISSING: $name"
  fi
done
```

Expected: все `FOUND` с non-trivial size (> 200 bytes). Каждый `MISSING` — red flag для stage в Task 5.

- [ ] **Step 4.3: Count rendered reels**

Run:
```bash
REELS_COUNT=$(find data/artifacts/${NEW_JOB_ID}/reels -name '*.mp4' 2>/dev/null | wc -l)
echo "Reels: $REELS_COUNT"
if [[ $REELS_COUNT -gt 0 ]]; then
  find data/artifacts/${NEW_JOB_ID}/reels -name '*.mp4' -printf '%P\t%s bytes\n' | sort
fi
```

Expected: `≥ 3`, каждый mp4 `≥ 1_000_000` bytes (1 MB — sanity check на non-empty render).

- [ ] **Step 4.4: Probe each reel for real duration**

Run:
```bash
for reel in data/artifacts/${NEW_JOB_ID}/reels/*.mp4; do
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$reel" 2>/dev/null)
  echo "$(basename "$reel")\t${dur}s"
done | sort
```

Expected: каждый reel `20 ≤ dur ≤ 120` сек. Если все reels имеют `dur = 0` или `dur < 5` — render не состоялся, mp4 битые.

- [ ] **Step 4.5: Record artifacts summary**

Дописать в `evidence-inventory.md`:
```markdown
## Task 4: Artifacts
- Artifacts tree: <X files, total Y MB>
- JSON dumps present: [canvas_full, extraction_full, story_script, reel_plan, analysis_summary, composer_breakdown]
- JSON dumps MISSING: <list>
- Reels rendered: <N>
- Reel duration distribution: min=<a>s, median=<b>s, max=<c>s
- Reel size distribution: min=<X>MB, max=<Y>MB
```

---

## Task 5: Stage-by-stage verification against memory

Для каждого stage — проверка конкретного критерия. Если критерий fail → записать в `evidence-inventory.md` под `## Task 5 / stage <name> / FAIL` с raw data, и идти на следующий stage (не прерывать весь план — собираем полную картину).

- [ ] **Step 5.1: Transcribe stage**

Критерий: транскрипт не пустой, word-level timestamps присутствуют.

Run:
```bash
TRANSCRIPT=$(find data/artifacts/${NEW_JOB_ID}/text -name 'transcript*.json' -o -name 'cleaned*.json' 2>/dev/null | head -1)
echo "Transcript file: $TRANSCRIPT"
if [[ -n "$TRANSCRIPT" ]]; then
  python3 -c "
import json
d = json.load(open('$TRANSCRIPT'))
segs = d.get('segments') or d.get('words') or d
print('Type:', type(d).__name__)
print('Top-level keys:', list(d.keys()) if isinstance(d, dict) else 'LIST')
print('Segments/words count:', len(segs) if hasattr(segs,'__len__') else '?')
"
fi
```

Expected:
- Файл существует
- `len(segments) >= 10` для 11-мин видео (примерно 1 segment на минуту если грубо)
- Каждый segment имеет `start`, `end`, `text` (либо `word`, `start`, `end` для word-level)

Memory criterion: **«311 segments на 663 sec»** (из job cf3695e1). Для нашего видео ожидать сопоставимую плотность.

- [ ] **Step 5.2: Silence cut stage**

Критерий: `cleaned_transcript.json` существует, фильтры применены.

Run:
```bash
CLEANED=$(find data/artifacts/${NEW_JOB_ID}/text -name 'cleaned*.json' 2>/dev/null | head -1)
if [[ -n "$CLEANED" ]]; then
  python3 -c "
import json
d = json.load(open('$CLEANED'))
dur_before = d.get('original_duration_sec') or d.get('source_duration')
dur_after = d.get('duration_sec') or d.get('cleaned_duration')
fillers_removed = d.get('fillers_removed', '?')
print('Original:', dur_before, 'Cleaned:', dur_after, 'Fillers removed:', fillers_removed)
"
fi
```

Expected:
- `cleaned_duration < original_duration` (что-то вырезано)
- `cleaned_duration > 0.5 * original_duration` (не вырезали слишком много, иначе bug)

- [ ] **Step 5.3: Canvas stage**

Критерий из memory `videomaker-pipeline-reanimation-2026-04-21`: `themes >= 3, motifs >= 2` после quality gate scaling.

Run:
```bash
CANVAS=$(find data/artifacts/${NEW_JOB_ID} -name 'canvas*.json' 2>/dev/null | head -1)
echo "Canvas: $CANVAS"
if [[ -n "$CANVAS" ]]; then
  python3 -c "
import json
d = json.load(open('$CANVAS'))
themes = d.get('themes') or d.get('canvas', {}).get('themes') or []
motifs = d.get('motifs') or d.get('canvas', {}).get('motifs') or []
moments = d.get('candidate_moments') or d.get('moments') or []
print(f'themes={len(themes)} motifs={len(motifs)} moments={len(moments)}')
print('Quality gate thresholds from canvas_builder._quality_thresholds should be 2/5/2 for ≤15min video')
"
fi
```

Expected (для ≤ 15 min video per `canvas_builder._quality_thresholds`):
- `themes >= 2`
- `moments >= 5`
- `motifs >= 2`

Если canvas_*.json **не найден вовсе** — stage не dumpит артефакт. Искать в `logs/`:
```bash
grep -E 'canvas_snapshot_saved|canvas.*themes|canvas.*motifs' data/artifacts/${NEW_JOB_ID}/logs/*.log 2>/dev/null | head -20
```

- [ ] **Step 5.4: Extraction stage (6 agents)**

Критерий: evidence count > 0 после всех extraction agents.

Run:
```bash
EXTRACTION=$(find data/artifacts/${NEW_JOB_ID} -name 'extraction*.json' 2>/dev/null | head -1)
echo "Extraction: $EXTRACTION"
if [[ -n "$EXTRACTION" ]]; then
  python3 -c "
import json
d = json.load(open('$EXTRACTION'))
ev = d.get('evidence') or d.get('items') or d
n = len(ev) if hasattr(ev,'__len__') else 0
print(f'evidence_items={n}')
if n > 0 and isinstance(ev, list) and isinstance(ev[0], dict):
    roles = sorted(set(e.get('role') or e.get('kind','') for e in ev))
    print(f'roles: {roles}')
"
fi
```

Expected:
- `evidence_items >= 5` для 11-мин видео (memory: 31 evidence)
- Роли разнообразны (не всё одного kind)

- [ ] **Step 5.5: Reducer / ranking**

Критерий: reducer отдал top-K items с сохранением разнообразия.

Run:
```bash
RANKED=$(find data/artifacts/${NEW_JOB_ID} -name 'ranked*.json' -o -name 'reducer*.json' 2>/dev/null | head -1)
echo "Ranked: $RANKED"
if [[ -n "$RANKED" ]]; then
  python3 -c "
import json
d = json.load(open('$RANKED'))
items = d.get('ranked') or d.get('items') or d
n = len(items) if hasattr(items,'__len__') else 0
print(f'ranked_items={n}')
if n > 0:
    scores = [i.get('composite_score') or i.get('score') for i in items if isinstance(i,dict)]
    scores = [s for s in scores if s is not None]
    if scores:
        print(f'score range: {min(scores):.2f}..{max(scores):.2f}, mean={sum(scores)/len(scores):.2f}')
"
fi
```

Expected:
- `ranked_items >= 10` (memory: avg_composite_score 88.0)
- `min(score) > 0`, `max(score) <= 1.0` (normalized)

- [ ] **Step 5.6: Story doctor stage**

Критерий из memory: arc duration 45-55s, 5 segments (hook/setup/dev/peak/payoff).

Run:
```bash
STORY=$(find data/artifacts/${NEW_JOB_ID} -name 'story_script*.json' -o -name 'story_doctor*.json' 2>/dev/null | head -1)
echo "Story: $STORY"
if [[ -n "$STORY" ]]; then
  python3 -c "
import json
d = json.load(open('$STORY'))
segs = d.get('segments') or d.get('arc', {}).get('segments') or []
total = sum((s.get('duration') or (s.get('end',0)-s.get('start',0))) for s in segs)
roles = [s.get('role') for s in segs]
print(f'segments={len(segs)} total_duration={total:.1f}s')
print(f'roles: {roles}')
expected_roles = {'hook','setup','development','peak','payoff'}
missing = expected_roles - set(roles)
print(f'missing_roles: {missing}')
"
fi
```

Expected:
- `segments >= 3`
- `total_duration` между 30s и 90s
- Присутствуют хотя бы 3 из 5 canonical roles

Если `missing_roles == expected_roles` (все пропущены) — story_doctor не отработал или использовал другую roles taxonomy. Проверить `services/story_doctor.py:_fallback_script`.

- [ ] **Step 5.7: Rhythm check**

Критерий: rhythm check не зарежектил arc (rhythm_score >= _RHYTHM_MIN_ACCEPTABLE).

Run:
```bash
grep -E 'rhythm_critique|rhythm_score|rhythm_accepted|rhythm_iterations' data/artifacts/${NEW_JOB_ID}/logs/*.log 2>/dev/null | tail -10
```

Expected: строка вида `rhythm_score=0.Y accepted=true iterations=N`. Если видно `rhythm_score < 0.7` или `iterations > _RHYTHM_MAX_ITERATIONS` — deviation.

- [ ] **Step 5.8: Composer stage**

Критерий из memory: `reels_composer accepted=10, multi-segment reels >=1`.

Run:
```bash
COMPOSER=$(find data/artifacts/${NEW_JOB_ID} -name 'composer*.json' -o -name 'reel_plan*.json' 2>/dev/null | head -1)
echo "Composer: $COMPOSER"
if [[ -n "$COMPOSER" ]]; then
  python3 -c "
import json
d = json.load(open('$COMPOSER'))
reels = d.get('reels') or d.get('plans') or d
multi = sum(1 for r in reels if isinstance(r,dict) and len(r.get('segments',[])) > 1)
singles = sum(1 for r in reels if isinstance(r,dict) and len(r.get('segments',[])) == 1)
durs = [sum(s.get('duration',0) for s in r.get('segments',[])) for r in reels if isinstance(r,dict)]
print(f'reels={len(reels)} multi_segment={multi} single_segment={singles}')
if durs:
    print(f'duration range: {min(durs):.1f}..{max(durs):.1f}s, mean={sum(durs)/len(durs):.1f}s')
"
fi
grep -E 'composer_candidates_breakdown|composer.*accepted|backfilled from heuristic' data/artifacts/${NEW_JOB_ID}/logs/*.log 2>/dev/null | head -10
```

Expected:
- `reels >= 3` (memory: 10)
- `multi_segment >= 1` (memory: 1)
- Duration range внутри `[30, 90]`
- **RED FLAG из memory**: строка `backfilled from heuristic source pool` в logs означает что composer не смог собрать из arc и упал на evidence_singles — это был корневой симптом сломанного pipeline ДО реанимации.

- [ ] **Step 5.9: Closure validator**

Критерий из memory: `6 complete, 4 extended, 0 failed`.

Run:
```bash
grep -E 'closure_validator|closure.*(complete|extended|failed)|closure_check' data/artifacts/${NEW_JOB_ID}/logs/*.log 2>/dev/null | tail -20
```

Expected: логи про closure per reel, 0 `failed`. Если `failed > 0` — closure validator зарежектил arcs.

- [ ] **Step 5.10: Record full stage matrix**

Дописать в `evidence-inventory.md` таблицу:
```markdown
## Task 5: Stage-by-stage matrix

| Stage | Memory claim | Actual | Status |
|---|---|---|---|
| transcribe | 311 segs / 663s | <N segs / <X>s | PASS/FAIL |
| silence_cut | cleaned_dur < source_dur | <X>s -> <Y>s | PASS/FAIL |
| canvas | themes=3, motifs=2, moments=9 | themes=<a>, motifs=<b>, moments=<c> | PASS/FAIL |
| extraction | 31 evidence | <N> | PASS/FAIL |
| reducer | ranked top with avg 88 | <N> items, mean=<X> | PASS/FAIL |
| story_doctor | arc 53.8s, 5 segs, full roles | <total>s, <n> segs, missing=<set> | PASS/FAIL |
| rhythm | accepted | <accepted/rejected/iterations> | PASS/FAIL |
| composer | 10 accepted, 1 multi | <N> reels, <M> multi | PASS/FAIL |
| closure | 6 complete, 4 extended, 0 failed | <C>/<E>/<F> | PASS/FAIL |
| render | 10 mp4 ≥ 1MB | <N> mp4, sizes: ... | PASS/FAIL |
```

- [ ] **Step 5.11: Commit diagnostics so far**

```bash
git add docs/diagnostics/2026-04-21-bottom-up-verification/
git commit -m "docs(diagnostics): task 1-5 runtime verification data for job ${NEW_JOB_ID}"
```

---

## Task 6: Diagnose gaps

- [ ] **Step 6.1: Classify final outcome**

На основе stage-matrix из Step 5.10 выбрать ровно одну категорию:

- **CATEGORY A — `Pipeline fully works per memory`**: все stages PASS, reels >= 3, durations in range, closure failed=0. → план завершён, memory подтверждён. Переход к Task 7.0.
- **CATEGORY B — `Pipeline runs end-to-end but quality degrades`**: все stages PASS, но reels < 3 ИЛИ durations monotonic ~40s ИЛИ multi_segment=0 ИЛИ closure failures > 0. → Task 7.1-7.4 (targeted fixes).
- **CATEGORY C — `Pipeline crashes mid-way`**: один stage FAIL c missing artifact, final status != succeeded. → Task 7.5 (crash diagnosis).
- **CATEGORY D — `Pipeline appears to succeed but artifacts empty`**: status=succeeded, но reels count = 0 или mp4 < 1MB. → Task 7.6 (silent failure diagnosis).

- [ ] **Step 6.2: Locate first FAIL stage**

Идём сверху вниз по stage-matrix, находим ПЕРВЫЙ `FAIL`. Этот stage — root cause candidate. Все последующие FAIL могут быть каскадом этого первого.

Записать в `evidence-inventory.md`:
```markdown
## Task 6: Diagnosis
- Final category: <A|B|C|D>
- First failing stage: <stage name>
- Root cause hypothesis: <1-2 sentences pointing to specific file/function>
```

- [ ] **Step 6.3: Cross-check with research**

Сравнить диагноз со structural claims из `docs/viral-clipper-research-2026-04-21.md`:
- «Bottom-up assembly не может обеспечить closure» — если FAIL на closure → подтверждение research.
- «MIN_RANKED_ITEMS=60 hardcoded» — если FAIL на reducer с малым N → это тот баг.
- «Target duration как constraint, не как consequence» — если все durations ~40s → это оно.

Дописать:
```markdown
- Research alignment: <matches research claim X | contradicts research | independent finding>
```

---

## Task 7: Decision tree — which fix plan to spawn

Task 7 — **NOT execution**. Это маршрутизация: какой отдельный implementation plan написать после verification. Каждая ветка указывает конкретные файлы + функции + предполагаемое изменение.

- [ ] **Step 7.0: CATEGORY A — memory confirmed**

Действие: обновить user — «memory verified, pipeline работает end-to-end». Дальнейшая работа — quality improvements из Phase A ultraplan (`docs/plans/2026-04-21-ultraplan-three-pipelines.md`), не urgent fix.

Не писать новый plan. Завершить verification.

- [ ] **Step 7.1: CATEGORY B / Canvas deficit (themes<2 or moments<5)**

Root cause по memory reanimation: `canvas_builder._quality_thresholds` + `_fallback_limits` scale thresholds по длительности, но LLM всё равно возвращает мало themes.

Fix candidates:
1. `apps/backend/src/videomaker/services/canvas_builder.py:_fallback_limits` — поднять верхний порог для short video с 5 до 12 moments.
2. `apps/backend/src/videomaker/services/prompts_data/canvas_builder.md` (если есть) — усилить instruction на «возвращай минимум N themes».

Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-canvas.md` with two tasks (prompt change + fallback limits change + smoke rerun).

- [ ] **Step 7.2: CATEGORY B / Composer monotonic durations**

Root cause по research: composer не варьирует длину, все reels ~40s.

Fix candidates:
1. `apps/backend/src/videomaker/services/reels_composer.py:_split_arc_into_shorts` — добавить target_slots=[35,45,55,70] и для каждого искать nearest structural boundary.
2. Reuse уже написанный `apps/backend/src/videomaker/services/narrative/boundary_extender.py` как universal post-processor.

Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-composer-durations.md` — эквивалент Phase A.3 из ultraplan, но targeted.

- [ ] **Step 7.3: CATEGORY B / Closure failures > 0**

Root cause по research: `+8s tail` недостаточен для russian monologue payoff.

Fix candidates:
1. `apps/backend/src/videomaker/services/closure_validator.py` — увеличить search window с 8s до 35s (MAX_CLOSURE_EXTENSION из `services/narrative/constants.py`).
2. Добавить русские discourse markers из research Section 6.3 + 2.5 в closure regex.

Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-closure.md`.

- [ ] **Step 7.4: CATEGORY B / multi_segment = 0**

Root cause по memory reanimation: singles с composite 0.9+ обгоняют arc-based candidates 0.82, `_apply_arc_narrative_boost × 1.25` недостаточен.

Fix candidates:
1. `apps/backend/src/videomaker/services/reels_composer.py:_apply_arc_narrative_boost` — поднять multiplier 1.25 → 1.35.
2. Добавить hard constraint: минимум 30% reels должны быть multi-segment.

Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-multisegment.md`.

- [ ] **Step 7.5: CATEGORY C — crash**

Извлечь traceback:
```bash
grep -B2 -A20 -iE 'error|exception|traceback|critical' data/artifacts/${NEW_JOB_ID}/logs/*.log | head -80
grep -iE 'error|exception|traceback' docs/diagnostics/2026-04-21-bottom-up-verification/backend-startup.log | head -40
```

Идентифицировать:
- Module/file из traceback
- Line number
- Exception type

Если ошибка в конкретной функции — открыть её через `mcp__serena__find_symbol --include_body=true`, предложить diff. Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-crash-<module>.md`.

Если ошибка на LLM-вызове (timeout, quota, schema validation) — зафиксировать в user report, не писать code fix plan.

- [ ] **Step 7.6: CATEGORY D — silent success-with-empty-output**

Это самый подозрительный сценарий. Status=succeeded, но reels пустые или 0-byte.

Инспекция:
1. Проверить `jobs.db` запись:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('apps/backend/data/videomaker.db' if False else 'data/videomaker.db')  # correct path per repo layout
c = conn.execute('SELECT id,status,error FROM jobs WHERE id=?',('${NEW_JOB_ID}',))
print(c.fetchone())
"
```
2. Проверить `analysis_summary.json.stats` — может ли `accepted=0` но status=succeeded (logic bug).
3. Проверить ffmpeg exit code в render logs:
```bash
grep -iE 'ffmpeg.*exit|ffmpeg.*error|renderer.*failed' data/artifacts/${NEW_JOB_ID}/logs/*.log | head
```

Spawn plan: `docs/plans/2026-04-21-bottom-up-fix-silent-empty.md`.

- [ ] **Step 7.7: Cleanup dev processes**

Независимо от категории:
```bash
kill -TERM $RUN_PID 2>/dev/null || true
pkill -f 'uvicorn videomaker' 2>/dev/null || true
pkill -f 'pnpm dev' 2>/dev/null || true
```

- [ ] **Step 7.8: Final commit + user report**

```bash
git add docs/diagnostics/2026-04-21-bottom-up-verification/evidence-inventory.md
git commit -m "docs(diagnostics): bottom-up verification complete — category <A|B|C|D>"
git push origin feat/glm-provider
```

User report structure (в чат):
```
Bottom-up verification complete.

Test video: <path> (<dur>s)
Job ID: <NEW_JOB_ID>
Final status: <status>
Category: <A/B/C/D>
First failing stage: <stage>
Root cause hypothesis: <one sentence>

Memory claim "10/10 reels": <CONFIRMED | REFUTED | PARTIAL>

Next step: spawn <plan-file.md> if category != A, else proceed to ultraplan Phase A.
```

---

## Self-review checklist

**1. Spec coverage:**
- ✅ Runtime dev env setup — Task 2
- ✅ Test video selection — Task 1
- ✅ Run job end-to-end — Task 3
- ✅ Collect artifacts — Task 4
- ✅ Stage-by-stage checklist — Task 5 (10 stages)
- ✅ Numeric criteria per stage — Task 5 with Expected values
- ✅ Diagnose gaps — Task 6
- ✅ Decision tree for fixes — Task 7 (6 sub-branches)

**2. Placeholders:** Нет TODO / TBD. Каждая команда выполнима. Критерии — конкретные числа или булевы predicates.

**3. Type consistency:** Имена переменных (`NEW_JOB_ID`, `TEST_VIDEO`, `RUN_PID`) консистентны через Task 2-7. Имена файлов артефактов упоминаются единообразно.

**4. Edge cases:**
- Missing `.env` → Task 0.3 stops
- Missing deps → Task 0.5 + Task 2.2 retry
- No test video → Task 1.3 asks user
- Job timeout → Task 3.4 handles
- Missing JSON dumps → Task 4.2 marks MISSING, Task 5 falls back to log grep
- Crash → Task 7.5 extracts traceback

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-04-21-bottom-up-verification-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — я диспетчирую fresh subagent на каждую Task с review между ними. Подходит если ожидается несколько deviation'ов.

**2. Inline Execution** — выполняем Task за Task в текущей сессии с чекпоинтами. Подходит если время дороже изоляции.

Какой подход?
