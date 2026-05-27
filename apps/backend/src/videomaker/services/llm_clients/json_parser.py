"""JSON response parsing с нарастающим уровнем терпимости.

Стратегия: strict ``json.loads`` → снять fenced markdown → bracket-aware
извлечь outer JSON → ``json_repair`` для truncated output. Падает с
``LLMError`` только если repair не смог ничего выжать.
"""

from __future__ import annotations

import json
from typing import Any

from videomaker.services.llm_clients.base import LLMError


def parse_json_response(text: str) -> Any:
    """Парсит JSON из LLM-ответа с нарастающим уровнем терпимости.

    Стратегия (каждая ступень — попытка полностью разобрать строку):
    1. Строгий `json.loads`.
    2. Снять fenced markdown-обёртки (``` ... ```).
    3. Взять наибольший внешний объект/массив между первым `{` или `[` и
       парным closer — bracket-aware scan с учётом строк и escape.
    4. **json_repair** — чинит truncated output от LLM (обрезанные строки,
       незакрытые скобки, trailing запятые). Обязательный шаг, т.к. даже
       при лимите в 32K токенов Pass 3 иногда выходит за пределы.

    Падает с LLMError только если репейр не смог ничего выжать.
    """

    stripped = text.strip()
    if not stripped:
        raise LLMError("llm response is empty")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    unwrapped = _unwrap_fenced(stripped)
    if unwrapped != stripped:
        try:
            return json.loads(unwrapped)
        except json.JSONDecodeError:
            stripped = unwrapped

    segment = _extract_outer_json(stripped)
    if segment is not None:
        try:
            return json.loads(segment)
        except json.JSONDecodeError:
            pass

    repaired = _repair_json(stripped)
    if repaired is not None:
        return repaired

    raise LLMError(f"llm response is not valid JSON: {stripped[:200]!r}")


def _repair_json(text: str) -> Any | None:
    """Чинит truncated/малформный JSON через json_repair.

    Возвращает Python-объект или None, если repair дал пустой результат
    (пустой dict/list считаем валидным — модель просто ничего не нашла).
    """

    import json_repair

    try:
        result = json_repair.repair_json(
            text,
            return_objects=True,
            skip_json_loads=True,
        )
    except (ValueError, TypeError):
        return None
    if result is None or result == "":
        return None
    if isinstance(result, str):
        return None
    return result


def _unwrap_fenced(text: str) -> str:
    lines = text.splitlines()
    fenced_start = None
    fenced_end = None
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line.startswith("```"):
            if fenced_start is None:
                fenced_start = i
            else:
                fenced_end = i
                break
    if fenced_start is not None and fenced_end is not None:
        return "\n".join(lines[fenced_start + 1 : fenced_end]).strip()
    return text


def _extract_outer_json(text: str) -> str | None:
    first_obj = text.find("{")
    first_arr = text.find("[")
    candidates = [pos for pos in (first_obj, first_arr) if pos != -1]
    if not candidates:
        return None
    start = min(candidates)
    opener = text[start]
    closer = "}" if opener == "{" else "]"

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
