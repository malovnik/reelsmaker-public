"""Сборка PublerScheduleRequest из доменных данных."""
from __future__ import annotations

from videomaker.models.scheduler import PublerNetwork, ScheduleAssignmentRow
from videomaker.services.publer.schemas import (
    PublerAccountTarget,
    PublerBulk,
    PublerInstagramNetwork,
    PublerMediaRef,
    PublerPost,
    PublerReelDetails,
    PublerScheduleRequest,
    PublerShortDetails,
    PublerYoutubeNetwork,
)

LABEL = "videomaker-auto"


def build_schedule_request(
    *,
    assignments: list[ScheduleAssignmentRow],
    media_refs_by_assignment_id: dict[int, PublerMediaRef],
) -> PublerScheduleRequest:
    """Каждое assignment → отдельный PublerPost (уникальный caption per account).

    Publer bulk требует отдельный `PublerPost` для каждой пары caption×account,
    потому что в одном посте `text` общий для всех targets. Мы генерим
    персонализированный caption на каждый аккаунт, поэтому склеиваем список
    посылок один-к-одному.

    Labels: `videomaker-auto` + `campaign-{id}` — для фильтрации в Publer UI.
    """
    posts: list[PublerPost] = []
    for assignment in assignments:
        media = media_refs_by_assignment_id[assignment.id]
        networks: dict[str, PublerInstagramNetwork | PublerYoutubeNetwork]
        if assignment.network == PublerNetwork.instagram.value:
            instagram_net = PublerInstagramNetwork(
                text=assignment.caption,
                media=[media],
                details=PublerReelDetails(feed=True),
            )
            networks = {"instagram": instagram_net}
        elif assignment.network == PublerNetwork.youtube.value:
            youtube_net = PublerYoutubeNetwork(
                title=assignment.title,
                text=assignment.caption,
                media=[media],
                details=PublerShortDetails(privacy="public"),
            )
            networks = {"youtube": youtube_net}
        else:
            raise ValueError(f"Неизвестный network: {assignment.network}")

        posts.append(
            PublerPost(
                networks=networks,
                accounts=[
                    PublerAccountTarget(
                        id=assignment.publer_account_id,
                        scheduled_at=assignment.scheduled_at_utc.isoformat(),
                        labels=[LABEL, f"campaign-{assignment.campaign_id}"],
                    )
                ],
            )
        )
    return PublerScheduleRequest(bulk=PublerBulk(state="scheduled", posts=posts))
