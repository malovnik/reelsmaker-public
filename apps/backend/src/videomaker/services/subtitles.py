"""ASS (Advanced SubStation Alpha) subtitle writer.

Генерирует ASS-файл, таймкоды которого привязаны к финальному рилсу (после
concat-склейки сегментов), а не к исходному видео. Для этого маппим каждое
слово из исходника (по source_start/end) в локальное время рилса.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from videomaker.services.transcribers.base import TranscribedWord


@dataclass(slots=True)
class SubtitleStyle:
    """Параметры ASS-стиля. Семантика `back_colour` зависит от `border_style`:

    * `border_style=1` (outline + shadow) — `back_colour` рисуется как тень
      текста.
    * `border_style=3` (opaque box) — `back_colour` используется для подложки
      под текстом; alpha управляет прозрачностью.
    """

    font: str = "Arial"
    size: int = 64
    primary_colour: str = "&H00FFFFFF&"
    outline_colour: str = "&H00000000&"
    back_colour: str = "&H64000000&"
    outline: float = 3.0
    shadow: float = 1.0
    margin_v: int = 200
    alignment: int = 2  # bottom-center
    bold: int = -1
    italic: int = 0
    border_style: int = 1
    # Горизонтальные поля текста относительно PlayResX. libass использует их
    # для авто-переноса длинных строк (и как отступ от левого/правого краёв
    # при alignment=2/5/8). Safe-zone-aware значения из resolve_style().
    margin_l: int = 40
    margin_r: int = 40
    # Wrap/line params. По умолчанию воспроизводим legacy-поведение
    # (4-6 слов, до 3 сек, flush на пунктуации) через ``wrap_mode="legacy"``.
    # Любое явное значение ``chars``/``sentence``/``word`` включает новую
    # логику разбиения, учитывающую ``max_lines`` и ``max_chars_per_line``.
    wrap_mode: str = "legacy"
    max_lines: int = 2
    max_chars_per_line: int = 30
    # Free-position override. Если оба поля заданы — в каждый dialogue event
    # добавляется ``{\pos(x,y)}`` в пиксельных координатах canvas'а (libass
    # центрирует текст по alignment=5 middle-center в этой точке).
    pos_x_px: int | None = None
    pos_y_px: int | None = None


@dataclass(slots=True)
class SubtitleReelSpec:
    reel_id: str
    segments: list[tuple[float, float]]  # (source_start, source_end)
    words: list[TranscribedWord]         # весь пул слов из исходного транскрипта
    play_resx: int = 1080
    play_resy: int = 1920
    style: SubtitleStyle = field(default_factory=SubtitleStyle)


def build_ass_for_reel(spec: SubtitleReelSpec) -> str:
    lines: list[str] = []
    lines.extend(_ass_header(spec))
    lines.append("")
    lines.extend(_ass_styles(spec.style))
    lines.append("")
    lines.extend(_ass_events(spec))
    return "\n".join(lines) + "\n"


def write_ass(spec: SubtitleReelSpec, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_ass_for_reel(spec), encoding="utf-8")
    return destination


def _ass_header(spec: SubtitleReelSpec) -> list[str]:
    return [
        "[Script Info]",
        "ScriptType: v4.00+",
        "Collisions: Normal",
        f"PlayResX: {spec.play_resx}",
        f"PlayResY: {spec.play_resy}",
        "Timer: 100.0000",
        "ScaledBorderAndShadow: yes",
    ]


def _ass_styles(style: SubtitleStyle) -> list[str]:
    return [
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,{style.font},{style.size},{style.primary_colour},"
            f"&H000000FF&,{style.outline_colour},{style.back_colour},"
            f"{style.bold},{style.italic},0,0,"
            f"100,100,0,0,{style.border_style},{style.outline},{style.shadow},"
            f"{style.alignment},{style.margin_l},{style.margin_r},{style.margin_v},1"
        ),
    ]


def _ass_events(spec: SubtitleReelSpec) -> list[str]:
    lines = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for dialogue in _compose_dialogue_lines(spec):
        lines.append(dialogue)
    return lines


_SENTENCE_TERMINATORS = (".", "!", "?", "…", "。", "！", "？")


def _compose_dialogue_lines(spec: SubtitleReelSpec) -> list[str]:
    """Группирует слова в фразы с учётом ``wrap_mode`` из стиля.

    * ``legacy`` — старое поведение: 4-6 слов, до 3 сек, flush на пунктуации.
    * ``chars`` — до ``max_chars_per_line × max_lines`` знаков включая пробелы,
      сверху ограничение ``max_lines`` строк с переносом по словам.
    * ``sentence`` — один субтитр = одно предложение (до знака препинания),
      внутри разбивается на ``max_lines`` строк.
    * ``word`` — каждое слово — отдельный субтитр (kinetic-typography).

    Ключевое правило: между segments всегда идёт принудительный flush — иначе
    слова из далёких мест исходника склеиваются в одну субтитровую реплику.
    """

    mode = spec.style.wrap_mode
    if mode == "word":
        return _compose_word_by_word(spec)
    if mode == "sentence":
        return _compose_by_sentence(spec)
    if mode == "chars":
        return _compose_by_chars(spec)
    return _compose_legacy(spec)


def _iter_segment_words(
    spec: SubtitleReelSpec,
) -> list[tuple[float, float, str, bool]]:
    """Нормализованный поток: (local_start, local_end, word, segment_boundary).

    ``segment_boundary=True`` — это последнее слово segment'а, после него
    consumer делает flush перед переходом к следующему segment'у.
    """

    flow: list[tuple[float, float, str, bool]] = []
    offset = 0.0
    for segment_start, segment_end in spec.segments:
        words_in_segment = [
            w for w in spec.words if segment_start <= w.start < segment_end and w.end > segment_start
        ]
        for idx, word in enumerate(words_in_segment):
            local_start = max(0.0, word.start - segment_start) + offset
            local_end = min(segment_end - segment_start, word.end - segment_start) + offset
            if local_end <= local_start:
                continue
            is_last = idx == len(words_in_segment) - 1
            flow.append((local_start, local_end, word.word, is_last))
        offset += max(0.0, segment_end - segment_start)
    return flow


def _compose_legacy(spec: SubtitleReelSpec) -> list[str]:
    results: list[str] = []
    phrase_words: list[tuple[float, float, str]] = []
    for local_start, local_end, word, segment_boundary in _iter_segment_words(spec):
        phrase_words.append((local_start, local_end, word))
        span = phrase_words[-1][1] - phrase_words[0][0]
        if len(phrase_words) >= 6 or span >= 3.0 or word.endswith(_SENTENCE_TERMINATORS) or segment_boundary:
            results.append(_dialogue_line(phrase_words, spec.style))
            phrase_words = []
    if phrase_words:
        results.append(_dialogue_line(phrase_words, spec.style))
    return results


def _compose_word_by_word(spec: SubtitleReelSpec) -> list[str]:
    results: list[str] = []
    for local_start, local_end, word, _boundary in _iter_segment_words(spec):
        results.append(_dialogue_line([(local_start, local_end, word)], spec.style))
    return results


def _compose_by_sentence(spec: SubtitleReelSpec) -> list[str]:
    results: list[str] = []
    buf: list[tuple[float, float, str]] = []
    for local_start, local_end, word, boundary in _iter_segment_words(spec):
        buf.append((local_start, local_end, word))
        if word.endswith(_SENTENCE_TERMINATORS) or boundary:
            results.append(_dialogue_line(buf, spec.style))
            buf = []
    if buf:
        results.append(_dialogue_line(buf, spec.style))
    return results


def _compose_by_chars(spec: SubtitleReelSpec) -> list[str]:
    """Chars-mode: короткие читаемые блоки. Максимум блока ровно ``max_chars
    × max_lines`` знаков включая пробелы между словами. На пунктуации flush.

    Важно: flush-проверка выполняется ДО добавления слова; если уже набранный
    буфер + новое слово превысит capacity — текущий буфер уходит в dialogue
    одним выстрелом, новое слово открывает следующий блок. Это гарантирует,
    что ``_wrap_into_lines`` никогда не получит на вход перелив.
    """

    style = spec.style
    max_chars = max(1, style.max_chars_per_line)
    max_lines = max(1, style.max_lines)
    capacity = max_chars * max_lines
    results: list[str] = []
    buf: list[tuple[float, float, str]] = []
    current_chars = 0

    def _flush() -> None:
        nonlocal buf, current_chars
        if buf:
            results.append(_dialogue_line(buf, style))
            buf = []
            current_chars = 0

    for local_start, local_end, word, boundary in _iter_segment_words(spec):
        word_len = len(word)
        separator = 1 if buf else 0
        projected = current_chars + separator + word_len
        if buf and projected > capacity:
            _flush()
            separator = 0
        buf.append((local_start, local_end, word))
        current_chars += separator + word_len if current_chars else word_len
        if word.endswith(_SENTENCE_TERMINATORS) or boundary:
            _flush()
    _flush()
    return results


def _dialogue_line(
    phrase_words: list[tuple[float, float, str]],
    style: SubtitleStyle,
) -> str:
    start = phrase_words[0][0]
    end = phrase_words[-1][1]
    raw_text = " ".join(word for _, _, word in phrase_words)
    wrapped = _wrap_into_lines(raw_text, style.max_lines, style.max_chars_per_line, style.wrap_mode)
    text = _ass_escape(wrapped)
    pos_tag = ""
    if style.pos_x_px is not None and style.pos_y_px is not None:
        pos_tag = f"{{\\pos({int(style.pos_x_px)},{int(style.pos_y_px)})}}"
    return (
        f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},Default,,0,0,0,,"
        f"{pos_tag}{text}"
    )


def _wrap_into_lines(
    text: str,
    max_lines: int,
    max_chars: int,
    mode: str,
) -> str:
    """Жадно переносит слова по строкам, строго соблюдая ``max_chars`` на
    каждой строке. Поведение на edge cases:

    * ``mode='word'`` или ``max_lines<=1`` — возвращаем текст как есть.
    * Слово длиннее ``max_chars`` — кладём его на собственную строку
      (не режем внутри слова, рендер может обрезать — лучше так, чем
      сломать смысл).
    * Если набралось больше, чем ``max_lines`` строк — оставшийся хвост
      склеиваем с последней кепт-строкой. Это единственный случай перелива;
      возникает только если входной текст длиннее ``max_lines × max_chars``.
      ``_compose_by_chars`` гарантирует, что такого не произойдёт.
    """

    if mode == "word" or max_lines <= 1:
        return text
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) >= max_chars:
            # Слово само по себе не влезает — отдельная строка.
            if current:
                lines.append(current)
                current = ""
            lines.append(word)
            continue
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        kept = lines[: max_lines - 1]
        overflow_tail = " ".join(lines[max_lines - 1 :])
        lines = [*kept, overflow_tail]
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - hours * 3600 - minutes * 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def _ass_escape(text: str) -> str:
    """Экранирование для ASS Dialogue-строки.

    * `\\`, `{`, `}` — спецсимволы override-блоков.
    * `\\n` → `\\N` — ASS hard break.
    * `\\r` удаляется (CR не является валидной инструкцией в dialogue).
    * `\\t` → пробел (таб в ASS dialogue интерпретируется как часть команды
      и ломает parser libass).
    """
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r", "")
        .replace("\t", " ")
        .replace("\n", "\\N")
    )
