"""
Manual referral point adjustment for the admin panel.

Implementation note: to avoid a second, parallel "points" concept that could
drift out of sync with the real referral/unlock logic, manually-granted
points are represented as ordinary Referral rows pointing at a synthetic
placeholder "referred user" (negative telegram_id, username "[manual]").
This lets them flow through the exact same pool/assign/revoke code path
(common/referral_logic.py) as genuine referrals -- including participating
in the 3-per-slot batching and the section-choice prompt.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.models import AdminAction, Referral, User
from common.referral_logic import revoke_referral

MANUAL_USERNAME = "[manual]"


async def _next_synthetic_id(session: AsyncSession) -> int:
    lowest = await session.scalar(select(User.telegram_id).order_by(User.telegram_id.asc()).limit(1))
    if lowest is None or lowest >= 0:
        return -1
    return lowest - 1


async def manual_add_points(
    session: AsyncSession, admin_username: str, target_user_id: int, count: int
) -> list[int]:
    target = await session.get(User, target_user_id)
    if target is None:
        raise ValueError(f"User {target_user_id} not found")

    created_ids = []
    for _ in range(count):
        synthetic_id = await _next_synthetic_id(session)
        placeholder = User(
            telegram_id=synthetic_id,
            username=MANUAL_USERNAME,
            full_name="Manual admin grant",
            is_verified_member=True,
            ever_verified=True,
        )
        session.add(placeholder)
        await session.flush()

        ref = Referral(
            referrer_id=target_user_id,
            referred_id=synthetic_id,
            was_fresh_at_landing=True,
            is_valid=True,
        )
        session.add(ref)
        await session.flush()
        created_ids.append(ref.id)

    session.add(
        AdminAction(
            admin_username=admin_username,
            action_type="manual_add_points",
            target_user_id=target_user_id,
            old_value=None,
            new_value=json.dumps({"count": count, "referral_ids": created_ids}),
            created_at=datetime.now(timezone.utc),
        )
    )
    return created_ids


async def manual_revoke_points(
    session: AsyncSession, admin_username: str, target_user_id: int, count: int
) -> list[int]:
    # Oldest-unassigned first (no cascading section re-lock), then oldest
    # assigned (may trigger a section re-lock via revoke_referral).
    candidates = (
        await session.scalars(
            select(Referral)
            .where(Referral.referrer_id == target_user_id, Referral.is_valid.is_(True))
            .order_by(Referral.section_assigned.is_(None).desc(), Referral.created_at.asc())
            .limit(count)
        )
    ).all()

    revoked_ids = []
    relocked_sections = []
    for ref in candidates:
        relocked = await revoke_referral(session, ref)
        if relocked:
            relocked_sections.append(relocked.value)
        revoked_ids.append(ref.id)

    session.add(
        AdminAction(
            admin_username=admin_username,
            action_type="manual_revoke_points",
            target_user_id=target_user_id,
            old_value=None,
            new_value=json.dumps({"count": len(revoked_ids), "referral_ids": revoked_ids, "relocked_sections": relocked_sections}),
            created_at=datetime.now(timezone.utc),
        )
    )
    return revoked_ids
