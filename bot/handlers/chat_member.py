"""
Requires the bot to be an admin in all 4 required channels (confirmed) so it
receives chat_member update events for them. We match by channel username
since that's what we were given for the gate channels (no numeric ids).
"""
import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards.inline import gate_channels_keyboard
from bot.services.membership import MEMBER_STATUSES, is_fully_verified
from common.config import get_settings
from common.db.models import User
from common.referral_logic import (
    activate_referral,
    get_referral_for_referred,
    referral_progress,
    should_prompt_section_choice,
)

logger = logging.getLogger(__name__)
router = Router(name="chat_member")
settings = get_settings()

REQUIRED_USERNAMES = {c["username"] for c in settings.required_channels}
_CHANNEL_BY_USERNAME = {c["username"]: c for c in settings.required_channels}


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, session: AsyncSession, bot: Bot):
    chat_username = event.chat.username
    if not chat_username or chat_username not in REQUIRED_USERNAMES:
        return

    target_user_id = event.new_chat_member.user.id
    user = await session.get(User, target_user_id)
    if user is None:
        return  # not someone the bot has ever seen via /start

    was_member = event.old_chat_member.status in MEMBER_STATUSES
    is_member_now = event.new_chat_member.status in MEMBER_STATUSES

    if was_member and not is_member_now:
        # Left this required channel -> re-check ALL 4 to update the overall flag.
        # Note: this only affects THIS user's own access to gated content --
        # it deliberately does NOT touch any Referral row. Once a referral is
        # credited to the referrer, it's permanent (product decision: the
        # referrer has no control over what their friend does afterward, so
        # they shouldn't lose progress or an unlocked section because of it).
        fully_verified = await is_fully_verified(bot, target_user_id)
        if user.is_verified_member and not fully_verified:
            user.is_verified_member = False
            user.last_membership_check = datetime.now(timezone.utc)
            await session.flush()
            left_channel = _CHANNEL_BY_USERNAME.get(chat_username)
            try:
                await bot.send_message(
                    target_user_id,
                    texts.left_channel_notice(),
                    reply_markup=gate_channels_keyboard(channels=[left_channel] if left_channel else None),
                )
            except Exception:
                pass

    elif not was_member and is_member_now:
        # Rejoined this channel -> re-check all 4; if now fully verified, restore.
        fully_verified = await is_fully_verified(bot, target_user_id)
        if fully_verified and not user.is_verified_member:
            user.is_verified_member = True
            user.last_membership_check = datetime.now(timezone.utc)
            await session.flush()
            referral = await get_referral_for_referred(session, target_user_id)
            if referral is not None:
                was_valid_before = referral.is_valid
                await activate_referral(session, referral)
                await session.flush()
                referrer_id = referral.referrer_id

                # Only notify on a genuine first-time validation. Referrals
                # are now permanent once earned (see comment above), so a
                # rejoin after an already-valid referral shouldn't re-fire
                # the notification.
                if referral.is_valid and not was_valid_before:
                    progress = await referral_progress(session, referrer_id)
                    try:
                        await bot.send_message(
                            referrer_id,
                            texts.friend_joined_notice(
                                event.new_chat_member.user.full_name,
                                progress["in_progress"],
                                progress["target"],
                                texts.squares(progress["in_progress"], progress["target"]),
                            ),
                        )
                    except Exception:
                        pass

                available = await should_prompt_section_choice(session, referrer_id)
                if available:
                    from bot.handlers.referral import send_section_choice_prompt

                    await send_section_choice_prompt(bot, referrer_id, available)
