import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards.inline import gate_channels_keyboard
from bot.services.membership import check_all_required, missing_channels
from bot.services.menu_render import send_main_menu
from common.db.models import User
from common.referral_logic import (
    activate_referral,
    get_or_create_user,
    get_referral_for_referred,
    record_referral_landing,
    referral_progress,
    should_prompt_section_choice,
)

logger = logging.getLogger(__name__)
router = Router(name="start")


def _parse_ref_payload(command: CommandObject) -> int | None:
    if not command.args:
        return None
    args = command.args.strip()
    if args.startswith("ref_"):
        try:
            return int(args.removeprefix("ref_"))
        except ValueError:
            return None
    return None


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    user, is_new = await get_or_create_user(
        session, user_id, message.from_user.username, message.from_user.full_name
    )
    user.start_count = (user.start_count or 0) + 1

    if is_new:
        referrer_id = _parse_ref_payload(command)
        if referrer_id:
            # Capture membership state RIGHT NOW, before this user has a chance
            # to join anything -- this is what decides was_fresh_at_landing.
            results = await check_all_required(bot, user_id)
            was_fresh = not any(results.values())
            user.landed_via_referrer_id = referrer_id
            await record_referral_landing(session, referred_id=user_id, referrer_id=referrer_id, was_fresh=was_fresh)
            await session.flush()

    if user.is_verified_member:
        await send_main_menu(message, session, user_id, message.from_user.full_name or "do'stim")
        return

    await message.answer(texts.gate_message(), reply_markup=gate_channels_keyboard(), disable_web_page_preview=True)


@router.callback_query(F.data == "gate_check")
async def cb_gate_check(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user = await session.get(User, user_id)
    if user is None:
        user, _ = await get_or_create_user(session, user_id, callback.from_user.username, callback.from_user.full_name)

    results = await check_all_required(bot, user_id)
    now_verified = all(results.values())

    from datetime import datetime, timezone

    was_verified_before = user.is_verified_member
    user.is_verified_member = now_verified
    user.last_membership_check = datetime.now(timezone.utc)

    if now_verified and not was_verified_before:
        # If this user landed via a referral link, this is the moment the
        # referral becomes (or re-becomes) valid.
        referral = await get_referral_for_referred(session, user_id)
        if referral is not None:
            await activate_referral(session, referral)
            await session.flush()
            referrer_id = referral.referrer_id

            # Notify the referrer immediately that a friend joined, with live
            # progress -- independent of whether this completes a batch of 3.
            progress = await referral_progress(session, referrer_id)
            try:
                await bot.send_message(
                    referrer_id,
                    texts.friend_joined_notice(
                        callback.from_user.full_name,
                        progress["in_progress"],
                        progress["target"],
                        texts.squares(progress["in_progress"], progress["target"]),
                    ),
                )
            except Exception:
                pass  # referrer may have blocked the bot -- don't let this break verification

            available = await should_prompt_section_choice(session, referrer_id)
            if available:
                from bot.handlers.referral import send_section_choice_prompt

                await send_section_choice_prompt(bot, referrer_id, available)

    if now_verified:
        await callback.answer("✅ Tabriklaymiz!")
        await callback.message.delete()
        await send_main_menu(callback.message, session, user_id, callback.from_user.full_name or "do'stim")
        return

    missing = missing_channels(results)
    await callback.answer()
    try:
        await callback.message.edit_text(
            texts.gate_message(missing_only=True, channels=missing),
            reply_markup=gate_channels_keyboard(missing_only=True, channels=missing),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
