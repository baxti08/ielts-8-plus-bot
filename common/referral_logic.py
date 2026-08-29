"""
Referral / section-unlock business logic.

Kept Telegram-free on purpose so both the bot and the admin panel (manual
point adjustment) drive the same rules and can't drift out of sync.

Key model, restated:
- Referral.was_fresh_at_landing: captured once, immutable. True only if the
  referred user was NOT already a member of any of the 4 gate channels at the
  moment they landed on the referral link.
- Referral.is_valid: was_fresh_at_landing AND the referred user is CURRENTLY
  verified (member of all 4). Flips with membership changes.
- Referral.section_assigned: NULL while sitting in the referrer's unassigned
  pool. Set once a batch of REFERRALS_PER_SLOT is spent to unlock a section.
- Re-lock semantics (flagged in the original spec as a strict reading, kept
  as-is per product decision): if a referral inside an assigned batch is
  revoked and that section's active+assigned count drops below the
  threshold, the WHOLE batch is unassigned (section_assigned -> NULL) and
  returns to the pool, and the section's SectionUnlock is deactivated. This
  only blocks *future* content access -- lessons already delivered via
  copyMessage cannot be un-sent/retroactively revoked through Telegram.
- Re-earning a section after a re-lock goes back through the manual
  "pick a section" prompt (confirmed product decision) -- it does not
  auto-reassign to the same section.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.db.models import GATED_SECTIONS, Referral, Section, SectionUnlock, User

settings = get_settings()
REFERRALS_PER_SLOT = settings.referrals_per_slot


async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    return await session.get(User, telegram_id)


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: Optional[str], full_name: str
) -> tuple[User, bool]:
    user = await session.get(User, telegram_id)
    if user:
        changed = False
        if username != user.username:
            user.username = username
            changed = True
        if full_name and full_name != user.full_name:
            user.full_name = full_name
            changed = True
        return user, False

    # Use INSERT ... ON CONFLICT DO NOTHING instead of a plain insert. Two
    # /start requests for the same brand-new user can race here (double-tap,
    # a redelivered Telegram update, etc.) -- both see no existing row above
    # and both attempt to insert. A plain insert would let the loser crash
    # with a duplicate-key IntegrityError; this makes the loser a no-op
    # instead, and the re-fetch below picks up whichever insert won.
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(User)
        .values(telegram_id=telegram_id, username=username, full_name=full_name or "")
        .on_conflict_do_nothing(index_elements=["telegram_id"])
    )
    await session.execute(stmt)
    await session.flush()
    user = await session.get(User, telegram_id)
    return user, True


async def record_referral_landing(
    session: AsyncSession, referred_id: int, referrer_id: int, was_fresh: bool
) -> Optional[Referral]:
    """
    Called on the FIRST /start with a ref_<id> payload for a brand-new user,
    before membership verification happens. No-ops if referrer == referred,
    referrer doesn't exist, or this user already has a referral row (a user
    can only ever be credited to the first referrer they landed from).
    """
    if referred_id == referrer_id:
        return None
    referrer = await session.get(User, referrer_id)
    if referrer is None:
        return None
    existing = await session.scalar(select(Referral).where(Referral.referred_id == referred_id))
    if existing:
        return existing
    ref = Referral(
        referrer_id=referrer_id,
        referred_id=referred_id,
        was_fresh_at_landing=was_fresh,
        is_valid=False,
    )
    session.add(ref)
    await session.flush()
    return ref


async def get_referral_for_referred(session: AsyncSession, referred_id: int) -> Optional[Referral]:
    """
    Explicit query instead of the ORM relationship (User.referral_received).
    Accessing that relationship lazily under AsyncSession raises
    MissingGreenlet unless it was eagerly loaded -- this avoids that trap.
    """
    return await session.scalar(select(Referral).where(Referral.referred_id == referred_id))


async def unassigned_pool_count(session: AsyncSession, referrer_id: int) -> int:
    result = await session.scalar(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_id == referrer_id,
            Referral.is_valid.is_(True),
            Referral.section_assigned.is_(None),
        )
    )
    return result or 0


async def active_unlocked_sections(session: AsyncSession, user_id: int) -> set[Section]:
    if user_id in settings.exempt_user_id_list:
        return set(GATED_SECTIONS)
    rows = await session.scalars(
        select(SectionUnlock.section).where(
            SectionUnlock.user_id == user_id, SectionUnlock.is_active.is_(True)
        )
    )
    return set(rows.all())


async def sections_available_to_unlock(session: AsyncSession, user_id: int) -> list[Section]:
    unlocked = await active_unlocked_sections(session, user_id)
    return [s for s in GATED_SECTIONS if s not in unlocked]


async def should_prompt_section_choice(session: AsyncSession, referrer_id: int) -> list[Section]:
    """Returns the list of sections to offer in the prompt, or [] if no prompt is due."""
    pool = await unassigned_pool_count(session, referrer_id)
    if pool < REFERRALS_PER_SLOT:
        return []
    available = await sections_available_to_unlock(session, referrer_id)
    return available


async def assign_batch_to_section(session: AsyncSession, referrer_id: int, section: Section) -> bool:
    """
    Spends the oldest REFERRALS_PER_SLOT unassigned valid referrals on `section`.
    Returns False if there weren't enough (race condition / stale prompt).
    """
    referrals = (
        await session.scalars(
            select(Referral)
            .where(
                Referral.referrer_id == referrer_id,
                Referral.is_valid.is_(True),
                Referral.section_assigned.is_(None),
            )
            .order_by(Referral.created_at.asc())
            .limit(REFERRALS_PER_SLOT)
        )
    ).all()
    if len(referrals) < REFERRALS_PER_SLOT:
        return False

    max_batch = await session.scalar(
        select(func.max(Referral.batch_number)).where(Referral.referrer_id == referrer_id)
    )
    next_batch = (max_batch or 0) + 1

    for r in referrals:
        r.section_assigned = section
        r.batch_number = next_batch

    unlock = await session.scalar(
        select(SectionUnlock).where(SectionUnlock.user_id == referrer_id, SectionUnlock.section == section)
    )
    if unlock:
        unlock.is_active = True
        unlock.unlocked_at = datetime.now(timezone.utc)
        unlock.relocked_at = None
    else:
        session.add(SectionUnlock(user_id=referrer_id, section=section, is_active=True))
    return True


async def activate_referral(session: AsyncSession, referral: Referral) -> None:
    """Referred user just became fully verified for the first time (or rejoined)."""
    if not referral.was_fresh_at_landing:
        return
    if not referral.is_valid:
        referral.is_valid = True
        referral.revoked_at = None


async def revoke_referral(session: AsyncSession, referral: Referral) -> Optional[Section]:
    """
    Referred user left a required channel. Returns the section that got
    re-locked as a side effect, if any, so the caller can notify the referrer.
    """
    if not referral.is_valid:
        return None
    referral.is_valid = False
    referral.revoked_at = datetime.now(timezone.utc)

    relocked_section: Optional[Section] = None
    if referral.section_assigned is not None:
        section = referral.section_assigned
        referrer_id = referral.referrer_id
        remaining_valid = await session.scalar(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == referrer_id,
                Referral.section_assigned == section,
                Referral.is_valid.is_(True),
            )
        )
        if (remaining_valid or 0) < REFERRALS_PER_SLOT:
            # Whole batch breaks: unassign every referral in it (valid or not)
            # and deactivate the unlock. See module docstring for rationale.
            batch_referrals = await session.scalars(
                select(Referral).where(
                    Referral.referrer_id == referrer_id,
                    Referral.section_assigned == section,
                )
            )
            for r in batch_referrals.all():
                r.section_assigned = None
                r.batch_number = None

            unlock = await session.scalar(
                select(SectionUnlock).where(
                    SectionUnlock.user_id == referrer_id, SectionUnlock.section == section
                )
            )
            if unlock and unlock.is_active:
                unlock.is_active = False
                unlock.relocked_at = datetime.now(timezone.utc)
                relocked_section = section
    return relocked_section


async def referral_progress(session: AsyncSession, referrer_id: int) -> dict:
    """Live counts for the '📊 Mening natijam' / result screens."""
    pool = await unassigned_pool_count(session, referrer_id)
    unlocked = await active_unlocked_sections(session, referrer_id)
    total_valid = await session.scalar(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_id == referrer_id, Referral.is_valid.is_(True)
        )
    )
    in_progress = min(pool, REFERRALS_PER_SLOT)
    all_unlocked = len(unlocked) >= len(GATED_SECTIONS)
    return {
        "pool": pool,
        "in_progress": in_progress,
        "total_valid": total_valid or 0,
        "unlocked_sections": unlocked,
        "all_unlocked": all_unlocked,
        "target": REFERRALS_PER_SLOT,
    }


async def is_section_unlocked(session: AsyncSession, user_id: int, section: Section) -> bool:
    if not section.is_gated:
        return True
    if user_id in settings.exempt_user_id_list:
        return True
    row = await session.scalar(
        select(SectionUnlock).where(
            SectionUnlock.user_id == user_id, SectionUnlock.section == section, SectionUnlock.is_active.is_(True)
        )
    )
    return row is not None
