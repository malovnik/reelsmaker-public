"""Scheduler service — фасад для создания Publer-кампаний из пула рилсов.

Единственный высокоуровневый entry-point, которым пользуется REST API,
чтобы собрать draft-кампанию: прогоняет (reel × account) пары через
caption_generator + preset_applier + scheduler_campaigns_store.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.logging import get_logger
from videomaker.models.reel_plan import ReelPlan
from videomaker.models.scheduler import (
    AssignmentStatus,
    PublerNetwork,
    ScheduleAssignmentRow,
    ScheduleCampaignRow,
)
from videomaker.services import (
    account_profiles_store,
    scheduler_campaigns_store,
)
from videomaker.services.llm_clients import LLMClient
from videomaker.services.publer.caption_generator import generate_caption
from videomaker.services.publer.preset_applier import apply_presets

log = get_logger(__name__)

_TIME_RE = re.compile(r"^(?P<hh>\d{2}):(?P<mm>\d{2})$")


def compute_scheduled_at_utc(
    *, date_iso: str, time_of_day: str, tz_name: str
) -> datetime:
    """Конвертирует локальное время в aware UTC datetime.

    Args:
        date_iso: ``YYYY-MM-DD``.
        time_of_day: ``HH:MM`` в локальной зоне.
        tz_name: IANA timezone (``Asia/Ho_Chi_Minh``, ``Europe/Moscow``, …).

    Returns:
        ``datetime`` с tzinfo=UTC, готовый к сохранению в ``scheduled_at_utc``.
    """
    y, m, d = (int(p) for p in date_iso.split("-"))
    hh, mm = (int(p) for p in time_of_day.split(":"))
    tz = ZoneInfo(tz_name)
    local = datetime(y, m, d, hh, mm, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC"))


def _compute_assignment_schedule(
    *,
    reel_index: int,
    account_index: int,
    total_accounts: int,
    mode: str,
    time_of_day: str,
    tz: str,
    dates: list[str] | None,
    single_day_date: str | None,
    single_day_interval_min: int,
    serial_start_date: str | None,
    serial_interval_days: int,
) -> datetime:
    """Считает ``scheduled_at_utc`` для одной пары (reel, account) по заданному режиму.

    Режимы:

    ``per_date``
        Распределение round-robin по списку ``dates``. Индекс в плоском списке
        (все пары reel × account) ``flat_idx = reel_index * total_accounts +
        account_index`` → ``dates[flat_idx % len(dates)]`` в ``time_of_day``.

    ``single_day``
        Все публикации в один день ``single_day_date``. Между соседними
        слотами — ``single_day_interval_min`` минут. Первая публикация — в
        ``time_of_day``, последующие — со смещением ``+interval_min × flat_idx``.

    ``serial``
        Серия публикаций с шагом ``serial_interval_days`` дней. Каждое уникальное
        видео (``reel_index``) — на своей дате: ``serial_start_date +
        reel_index × interval_days``. Все аккаунты одного видео публикуют в один
        день, но с небольшим jitter (2 минуты × ``account_index``), чтобы Publer
        не запускал их абсолютно одновременно.

    Args:
        reel_index: 0-based индекс уникального видео в пакете.
        account_index: 0-based индекс аккаунта внутри одного видео.
        total_accounts: Общее число аккаунтов в кампании (для round-robin).
        mode: ``per_date`` | ``single_day`` | ``serial``.
        time_of_day: ``HH:MM`` в локальной зоне ``tz``.
        tz: IANA timezone.
        dates: Список ``YYYY-MM-DD`` — обязателен при ``mode=per_date``.
        single_day_date: ``YYYY-MM-DD`` — обязателен при ``mode=single_day``.
        single_day_interval_min: Интервал между слотами в минутах.
        serial_start_date: ``YYYY-MM-DD`` базовой даты — обязателен при ``mode=serial``.
        serial_interval_days: Шаг между видео в днях.

    Returns:
        ``datetime`` с ``tzinfo=UTC``.

    Raises:
        ValueError: если ``mode`` не распознан или не заданы обязательные поля.
    """
    if mode == "per_date":
        if not dates:
            raise ValueError("dates обязательны при mode=per_date")
        flat_idx = reel_index * total_accounts + account_index
        date_iso = dates[flat_idx % len(dates)]
        return compute_scheduled_at_utc(
            date_iso=date_iso, time_of_day=time_of_day, tz_name=tz
        )

    if mode == "single_day":
        if not single_day_date:
            raise ValueError("single_day_date обязателен при mode=single_day")
        base = compute_scheduled_at_utc(
            date_iso=single_day_date, time_of_day=time_of_day, tz_name=tz
        )
        flat_idx = reel_index * total_accounts + account_index
        return base + timedelta(minutes=single_day_interval_min * flat_idx)

    if mode == "serial":
        if not serial_start_date:
            raise ValueError("serial_start_date обязателен при mode=serial")
        base = compute_scheduled_at_utc(
            date_iso=serial_start_date, time_of_day=time_of_day, tz_name=tz
        )
        day_offset = serial_interval_days * reel_index
        jitter = timedelta(minutes=2 * account_index)
        return base + timedelta(days=day_offset) + jitter

    raise ValueError(f"Unknown mode: {mode!r}")


async def build_campaign_from_pool(
    db: AsyncSession,
    *,
    name: str,
    reels: list[tuple[str, ReelPlan, int]],
    account_ids: list[str],
    time_of_day: str,
    tz: str,
    mode: Literal["per_date", "single_day", "serial"] = "per_date",
    dates: list[str] | None = None,
    single_day_date: str | None = None,
    single_day_interval_min: int = 60,
    serial_start_date: str | None = None,
    serial_interval_days: int = 1,
    llm: LLMClient,
) -> tuple[ScheduleCampaignRow, list[ScheduleAssignmentRow]]:
    """Создаёт ``ScheduleCampaignRow`` + draft-``ScheduleAssignmentRow`` для каждой
    пары (reel × account).

    Args:
        reels: список кортежей ``(job_id, reel_plan, reel_artifact_id)``.
        account_ids: Publer account IDs (24-hex), на которые публиковать.
        time_of_day: ``HH:MM`` в локальной зоне ``tz``.
        tz: IANA timezone.
        mode: Режим распределения — ``per_date`` / ``single_day`` / ``serial``.
            См. ``_compute_assignment_schedule`` для описания.
        dates: Для ``mode=per_date`` — список ``YYYY-MM-DD``, ассайнменты
            раскидываются round-robin.
        single_day_date: Для ``mode=single_day`` — день публикаций ``YYYY-MM-DD``.
        single_day_interval_min: Интервал между слотами в минутах (default 60).
        serial_start_date: Для ``mode=serial`` — базовая дата ``YYYY-MM-DD``.
        serial_interval_days: Шаг между видео в днях (default 1).
        llm: ``LLMClient`` для caption_generator (Flash Lite).

    Для каждой пары:
    - загружает ``AccountProfileRow`` (если нет — пропускает с warning);
    - генерит caption через ``caption_generator.generate_caption``;
    - применяет scoped + global пресеты в правильном порядке;
    - считает ``scheduled_at_utc`` по режиму ``mode``;
    - создаёт ``ScheduleAssignmentRow`` в статусе ``draft``.

    Returns:
        ``(campaign_row, [assignment_rows])`` — campaign создан в статусе
        ``draft``, assignments тоже draft (ready-to-review в UI).

    Raises:
        ValueError: пустой ``account_ids``, некорректный ``time_of_day``/``tz``,
            несогласованные поля режима (например, ``mode=per_date`` без ``dates``).
    """
    if mode not in ("per_date", "single_day", "serial"):
        raise ValueError(f"Unknown mode: {mode!r}")
    if not account_ids:
        raise ValueError("account_ids не могут быть пустыми")
    if mode == "per_date" and not dates:
        raise ValueError("dates не могут быть пустыми при mode=per_date")
    if mode == "single_day" and not single_day_date:
        raise ValueError("single_day_date обязателен при mode=single_day")
    if mode == "serial" and not serial_start_date:
        raise ValueError("serial_start_date обязателен при mode=serial")

    match = _TIME_RE.match(time_of_day)
    if not match:
        raise ValueError(
            f"time_of_day должен быть HH:MM, получено: {time_of_day!r}"
        )
    hh_val = int(match.group("hh"))
    mm_val = int(match.group("mm"))
    if not (0 <= hh_val <= 23 and 0 <= mm_val <= 59):
        raise ValueError(
            f"time_of_day вне допустимого диапазона (00:00-23:59): {time_of_day!r}"
        )
    try:
        ZoneInfo(tz)
    except Exception as exc:
        raise ValueError(f"Некорректный tz: {tz!r}") from exc

    # dates_json для хранения/UI — репрезентативный список дат режима.
    if mode == "per_date":
        dates_json: list[str] = list(dates or [])
    elif mode == "single_day":
        assert single_day_date is not None
        dates_json = [single_day_date]
    else:  # serial
        assert serial_start_date is not None
        dates_json = [serial_start_date]

    campaign = await scheduler_campaigns_store.create_campaign(
        db, name=name, tz=tz, time_of_day=time_of_day, dates=dates_json
    )

    assignments: list[ScheduleAssignmentRow] = []
    for reel_index, (job_id, reel, reel_artifact_id) in enumerate(reels):
        account_index = 0
        for account_id in account_ids:
            profile = await account_profiles_store.get_profile(db, account_id)
            if profile is None:
                log.warning(
                    "scheduler_skip_no_profile",
                    account_id=account_id,
                    reel_id=reel.reel_id,
                    job_id=job_id,
                )
                continue

            generated = await generate_caption(
                reel=reel, profile=profile, llm=llm
            )
            presets = await account_profiles_store.list_presets_for_scope(
                db, account_id=account_id
            )
            final_caption, applied_ids = apply_presets(
                generated_caption=generated.caption,
                presets=list(presets),
            )

            scheduled_at = _compute_assignment_schedule(
                reel_index=reel_index,
                account_index=account_index,
                total_accounts=len(account_ids),
                mode=mode,
                time_of_day=time_of_day,
                tz=tz,
                dates=dates,
                single_day_date=single_day_date,
                single_day_interval_min=single_day_interval_min,
                serial_start_date=serial_start_date,
                serial_interval_days=serial_interval_days,
            )

            title = (
                generated.title
                if profile.network == PublerNetwork.youtube.value
                else ""
            )

            assignment = await scheduler_campaigns_store.create_assignment(
                db,
                campaign_id=campaign.id,
                job_id=job_id,
                reel_artifact_id=reel_artifact_id,
                publer_account_id=account_id,
                network=profile.network,
                title=title,
                caption=final_caption,
                hashtags=generated.hashtags,
                applied_preset_ids=applied_ids,
                scheduled_at_utc=scheduled_at,
                status=AssignmentStatus.draft.value,
            )
            assignments.append(assignment)
            account_index += 1

    return campaign, assignments
