# Subtitle Sync Investigation — 2026-04-19

> Контекст: Phase 1 tech-debt cleanup. Пользователь сообщал о рассинхроне субтитров
> в сгенерированных рилсах, репро недоступно. Задача — закрыть окно рассинхрона
> safe guard'ом без изменения happy-path поведения.

## Hypothesis

В `_run_render_stage_via_project_graph` (`apps/backend/src/videomaker/services/
pipeline.py`) ASS-файл субтитров генерируется в двух точках:

1. **Ранняя генерация** — строка 1142 (внутри цикла `for plan in analysis_reels`),
   на основе исходных LLM-сегментов (`plan.segments`).
2. **Resync** — строка ~1752 (конец stage'а), на основе финальных `graph.cuts`
   после всех мутаций (pause compression → breath compression → filler removal →
   cut snap → rhythm-aware snap → J/L-cut).

Если между (1) и (2) произошла ошибка (OOM на VAD, сбой filler remover,
исключение в snap dispatcher) и stage не дошёл до resync — на диске остался
**ранний ASS из исходных сегментов**, который читает renderer. Каждая
мутация cuts сдвигала бы time-range внутри рилса → субтитры уезжают.

Даже при happy-path ранняя генерация — work-for-nothing: файл сразу же
перезаписывается в resync блоке (строка 1735 `if subtitle_paths_by_reel`).

## Что проверил

| Что | Вывод |
|---|---|
| Две точки `write_ass` в pipeline.py | Подтверждено: строки 1142 и 1752 |
| Все toggles, мутирующие `graph.cuts` | `punchline_pause_enabled`, `pause_compression_enabled`, `filler_removal_enabled`, `cut_snap_enabled`, `rhythm_aware_cuts_enabled`, `snap_strategy != "off"` |
| Resync покрывает все reels | Да, итерирует по `graphs` и использует `subtitle_paths_by_reel[g.reel_id]` → тот же путь |
| `perf_preview` доступен выше по коду | НЕТ — получался на строке 1220, ПОСЛЕ ранней генерации. Пришлось переместить выше |
| Renderer читает `graph.subtitle_path` | Да, путь проставляется в `build_project_graph` единожды, resync перезаписывает файл **по тому же пути** → renderer всегда читает актуальный |

## Conclusion

Ранняя `write_ass` на строке 1142 — legacy optimization, потерявшая смысл после
введения resync блока. Для Auto Mode / любой performance toggle она:

- бесполезна (перезаписывается в resync)
- потенциально опасна (остаётся на диске при сбое stage)

Поздняя resync уже гарантирует корректный ASS из `g.cuts`, который идентичен
финальному рендеру.

## Что поменял

**File:** `apps/backend/src/videomaker/services/pipeline.py`

1. Перенёс `perf_preview = await get_performance_settings(settings)` из строки
   1220 наверх, перед циклом `for plan in analysis_reels` (строка ~1107).
   Убрал дубликат на старом месте (переиспользуем переменную).
2. Добавил флаг `_needs_mutation_safe_resync` на основе 6 toggles, которые
   трогают `graph.cuts`.
3. Обернул ранний `write_ass(sub_spec, sub_path)` в guard: выполняется только
   если **ни один** mutation toggle не активен.

Resync блок на строке 1752 не трогал — он и раньше гарантировал финальный ASS.

### Behaviour matrix после фикса

| Сценарий | Ранний write_ass | Resync write_ass | Итоговый ASS |
|---|---|---|---|
| Все toggles off (legacy / debug) | ✅ делается | ❌ пропускается (цикл по graphs без работы — `subtitle_paths_by_reel` пуст только если graphs пуст) | Ранний (совпадает с финальным, cuts не мутировали) |
| Любой mutation toggle on (Auto Mode) | ❌ пропускается | ✅ делается | Resync из `g.cuts` |
| Stage упал между ранней и resync (при Auto Mode) | ❌ пропускается | — не дошло | **Файла нет** → renderer падает явно, а не рендерит desynced ASS |

## Follow-up (не входит в Phase 1)

- Рассмотреть удаление ранней генерации целиком — если resync стабилен во всех
  сценариях, она не нужна. Требует trace на пути `subtitle_paths_by_reel` +
  renderer'а: точно ли файл попадает в него только из graph.subtitle_path.
- Добавить метрику/лог: сколько раз ранняя генерация фактически произошла
  (ожидается ≈0 для production, где Auto Mode активен по умолчанию).
