# REFACTR-16 — API «перезапуск с шага X»

> **Этап:** 02
> **Шаг:** 17 из 67
> **Зависимости:** REFACTR-05 (карта pipeline stages), REFACTR-14 (Project модель).
> **Следующий шаг:** REFACTR-17 (копирование настроек)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** Pipeline restart = хирургия потока. Нельзя прервать работающую стадию грубо — нужен cancellation-token + чистка артефактов последующих стадий.

### R-PIPELINE-ENG
**Soul:** Каждая стадия = checkpoint. Без checkpoint-файлов restart невозможен. Если аудит выявил стадии без checkpoint — добавить их тут.

---

## ТРИЗ-принцип

*Принцип сегментации.* Pipeline разбит на стадии. Restart = «инвалидировать артефакты стадий ≥ X» + «запустить pipeline с стадии X».

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 16.1 Перечень стадий

Из REFACTR-05 зафиксирован граф. Возможные точки перезапуска (с эталонами checkpoint-файлов):

| Stage | Checkpoint-file | Reset action |
|-------|-----------------|--------------|
| transcribe | `transcript.json` | удалить + ререан |
| silence_cut | `segments.json` | удалить + ререан |
| llm_analysis | `ideas.json` | удалить + ререан |
| reel_compose | `reels.json` | удалить + ререан |
| render | `clips/`, `renders/` | удалить + ререан |

### 16.2 Endpoint спецификация

```
POST /api/projects/{project_id}/restart
Body:
{
  "from_stage": "transcribe" | "silence_cut" | "llm_analysis" | "reel_compose" | "render",
  "reason": string (optional, для логов)
}
Response 202: { job_id: string }
Response 409: { error: "pipeline_running" }  # если уже идёт
```

### 16.3 Реализация

`services/project_restart.py`:

```python
async def restart_from_stage(project_id: str, from_stage: Stage):
    # 1. Check no running pipeline for this project
    if await is_pipeline_running(project_id):
        raise PipelineBusyError()
    
    # 2. Invalidate artifacts for all stages >= from_stage
    await invalidate_artifacts(project_id, from_stage)
    
    # 3. Update stage_progress in Project
    await reset_stage_progress(project_id, from_stage)
    
    # 4. Spawn new job
    job_id = await spawn_pipeline_job(project_id, start_from=from_stage)
    return job_id
```

### 16.4 Cancellation

Если pipeline идёт — endpoint возвращает 409. Отмена текущего pipeline — отдельный endpoint `POST /api/projects/{id}/cancel` (уже существует или создаём).

### 16.5 Тесты

- [ ] Restart от transcribe — удалены все downstream artifacts, стадия начинается заново.
- [ ] Restart от render — транскрипция и идеи остаются, только render переделывается.
- [ ] Restart при running pipeline — 409.

### 16.6 Verification + Commit + лог + Serena memory

---

## GATE-чекпоинт

- [ ] Endpoint работает через `curl`.
- [ ] Артефакты downstream инвалидируются корректно.
- [ ] Stage_progress обновляется.
- [ ] Tests зелёные.

---

## Артефакт на выходе

`POST /api/projects/{id}/restart` + service + тесты.
