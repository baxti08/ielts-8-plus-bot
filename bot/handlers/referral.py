from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards.inline import (
    locked_section_keyboard,
    referral_link_share_keyboard,
    referral_share_button_keyboard,
    section_choice_keyboard,
)
from bot.keyboards.reply import BTN_MY_RESULT, BTN_REFERRAL_LINK
from common.db.models import GATED_SECTIONS, Section
from common.referral_logic import (
    REFERRALS_PER_SLOT,
    assign_batch_to_section,
    referral_progress,
    should_prompt_section_choice,
)

router = Router(name="referral")


async def send_section_choice_prompt(bot: Bot, referrer_id: int, available_sections: list[Section]) -> None:
    await bot.send_message(
        referrer_id,
        texts.choose_section_prompt(),
        reply_markup=section_choice_keyboard(available_sections),
    )


async def _pitch_text(session: AsyncSession, user_id: int) -> str:
    progress = await referral_progress(session, user_id)
    return texts.referral_pitch_block(
        progress["total_valid"], progress["target"], texts.squares(progress["total_valid"], progress["target"])
    )


@router.message(F.text == BTN_REFERRAL_LINK)
async def send_referral_link(message: Message):
    user_id = message.from_user.id
    await message.answer(
        texts.referral_post_message(user_id),
        reply_markup=referral_link_share_keyboard(user_id),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await message.answer(
        texts.referral_forward_hint(),
        reply_markup=referral_share_button_keyboard(user_id),
    )


@router.callback_query(F.data == "ref_link")
async def cb_referral_link(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    await callback.message.answer(
        texts.referral_post_message(user_id),
        reply_markup=referral_link_share_keyboard(user_id),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await callback.message.answer(
        texts.referral_forward_hint(),
        reply_markup=referral_share_button_keyboard(user_id),
    )


@router.callback_query(F.data == "ref_progress")
async def cb_referral_progress(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    text = await _pitch_text(session, callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=locked_section_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=locked_section_keyboard())


async def show_locked_section(message: Message, session: AsyncSession, section: Section) -> None:
    await message.answer(texts.locked_section_header(section))
    text = await _pitch_text(session, message.from_user.id)
    await message.answer(text, reply_markup=locked_section_keyboard())


@router.callback_query(F.data == "open_lessons")
async def cb_open_lessons(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    text = await _pitch_text(session, callback.from_user.id)
    await callback.message.answer(text, reply_markup=locked_section_keyboard())


@router.message(F.text == BTN_MY_RESULT)
async def show_my_result(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    progress = await referral_progress(session, user_id)
    n = progress["total_valid"]
    target = progress["target"]
    sq = texts.squares(n, target)

    if progress["all_unlocked"]:
        await message.answer(
            f"📊 Mening natijam\n\n🎉 Barcha bo'limlar ochilgan! Rahmat, {len(GATED_SECTIONS)} ta bo'limni "
            f"do'stlaringiz yordamida ochdingiz."
        )
        return

    await message.answer(texts.my_result_in_progress(n, target, sq), reply_markup=locked_section_keyboard())


@router.callback_query(F.data.startswith("choose_section:"))
async def cb_choose_section(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    section_value = callback.data.split(":", 1)[1]
    section = Section(section_value)
    user_id = callback.from_user.id

    ok = await assign_batch_to_section(session, user_id, section)
    await session.flush()

    if not ok:
        await callback.answer("Bu bo'lim uchun yetarli ball topilmadi.", show_alert=True)
        return

    await callback.answer("✅ Ochildi!")
    try:
        await callback.message.edit_text(texts.section_unlocked_notice(section.display_name))
    except Exception:
        await callback.message.answer(texts.section_unlocked_notice(section.display_name))

    # There may be another full batch already waiting (e.g. user had 6+ pooled).
    available = await should_prompt_section_choice(session, user_id)
    if available:
        await send_section_choice_prompt(bot, user_id, available)
