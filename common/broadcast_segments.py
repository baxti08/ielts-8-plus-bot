from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.models import GATED_SECTIONS, ContentDelivery, Referral, Section, User
from common.referral_logic import REFERRALS_PER_SLOT

MID_FUNNEL_THRESHOLD = len(GATED_SECTIONS) * REFERRALS_PER_SLOT  # 12 = 4 sections x 3 referrals

SEGMENTS = {
    "all": "Barcha foydalanuvchilar",
    "mid_funnel": f"{MID_FUNNEL_THRESHOLD} tadan kam taklif qilganlar (hali funnel ichida)",
    "unsubscribed": "Hozir barcha kanallarga a'zo bo'lmaganlar",
    "no_listening": "Listening hali olmaganlar",
    "no_reading": "Reading hali olmaganlar",
    "no_writing": "Writing hali olmaganlar",
    "no_speaking": "Speaking hali olmaganlar",
    "no_multilevel": "Multi-Level dars hali olmaganlar",
}

_NO_CONTENT_SECTION = {
    "no_listening": Section.listening,
    "no_reading": Section.reading,
    "no_writing": Section.writing,
    "no_speaking": Section.speaking,
    "no_multilevel": Section.multilevel,
}


def parse_exclude_ids(raw: str) -> list[int]:
    """Parses free-text admin input (comma or newline separated Telegram
    IDs) into a clean list of ints, silently skipping anything that isn't a
    valid integer rather than crashing on a typo or stray character."""
    if not raw:
        return []
    tokens = raw.replace("\n", ",").split(",")
    return [int(t.strip()) for t in tokens if t.strip().lstrip("-").isdigit()]


async def get_target_user_ids(
    session: AsyncSession, segment: str, exclude_ids: list[int] | None = None
) -> list[int]:
    if segment == "all":
        stmt = select(User.telegram_id).where(User.telegram_id > 0)
    elif segment == "unsubscribed":
        stmt = select(User.telegram_id).where(User.telegram_id > 0, User.is_verified_member.is_(False))
    elif segment == "mid_funnel":
        valid_counts = (
            select(Referral.referrer_id, func.count().label("cnt"))
            .where(Referral.is_valid.is_(True))
            .group_by(Referral.referrer_id)
            .subquery()
        )
        stmt = (
            select(User.telegram_id)
            .outerjoin(valid_counts, User.telegram_id == valid_counts.c.referrer_id)
            .where(User.telegram_id > 0, func.coalesce(valid_counts.c.cnt, 0) < MID_FUNNEL_THRESHOLD)
        )
    elif segment in _NO_CONTENT_SECTION:
        section = _NO_CONTENT_SECTION[segment]
        delivered_ids = select(ContentDelivery.user_id).where(ContentDelivery.section == section)
        stmt = select(User.telegram_id).where(User.telegram_id > 0, User.telegram_id.not_in(delivered_ids))
    else:
        raise ValueError(f"Unknown segment: {segment}")

    if exclude_ids:
        stmt = stmt.where(User.telegram_id.not_in(exclude_ids))

    result = await session.scalars(stmt)
    return list(result.all())
