"""
'Ko'proq funksiyalar' menu -- two additional referral-gated features that
don't fit the day-numbered lesson model the other 4 sections use:

- Speaking Recent Questions: a submenu with 2 options.
    - IELTS: copies 3 fixed "book" messages from a private source channel
      (the bot must be admin there; message ids are configured via
      SPEAKING_RECENT_BOOK_MESSAGE_IDS in .env).
    - Multi Level: content not ready yet, sends a "coming soon" notice.
- Writing AI Check + Feedback: not built yet, sends a "coming soon" notice
  directly (no submenu).

Both entries are locked until the user unlocks them via the same 3-invite
referral mechanism as the other 4 sections (see common/db/models.py
GATED_SECTIONS and common/referral_logic.py) -- per product decision, no
lock icon is shown on the buttons themselves; tapping a locked one instead
shows the same locked-section pitch used elsewhere.
"""
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.referral import show_locked_section
from bot.keyboards.inline import more_features_keyboard, speaking_recent_submenu_keyboard
from bot.keyboards.reply import BTN_MORE_FEATURES
from common.config import get_settings
from common.db.models import Section
from common.referral_logic import is_section_unlocked

router = Router(name="more_features")
settings = get_settings()

WRITING_AI_CHECK_COMING_SOON = "Tez soatlar ichida Writing AI Check + Feedback qo'shiladi⚡️"
SPEAKING_RECENT_MULTILEVEL_COMING_SOON = "Tez soatlar ichida Multi Level Recent Speaking Questions qo'shiladi⚡️"


@router.message(F.text == BTN_MORE_FEATURES)
async def open_more_features(message: Message):
    await message.answer("⚡️ Ko'proq funksiyalar:", reply_markup=more_features_keyboard())


@router.callback_query(F.data == "more:speaking_recent")
async def cb_speaking_recent_menu(callback: CallbackQuery, session: AsyncSession):
    section = Section.speaking_recent
    if not await is_section_unlocked(session, callback.from_user.id, section):
        await callback.answer()
        await show_locked_section(callback.message, session, section)
        return

    await callback.answer()
    await callback.message.answer(
        f"{section.display_name} — quyidagilardan birini tanlang:",
        reply_markup=speaking_recent_submenu_keyboard(),
    )


@router.callback_query(F.data == "speaking_recent:ielts")
async def cb_speaking_recent_ielts(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    section = Section.speaking_recent
    if not await is_section_unlocked(session, callback.from_user.id, section):
        await callback.answer()
        await show_locked_section(callback.message, session, section)
        return

    message_ids = settings.speaking_recent_book_message_id_list
    if not message_ids:
        await callback.answer("Hozircha materiallar yuklanmagan.", show_alert=True)
        return

    await callback.answer("⏳ Yuborilmoqda...")
    user_id = callback.from_user.id
    for message_id in message_ids:
        try:
            await bot.copy_message(
                chat_id=user_id, from_chat_id=settings.channel_speaking_recent_id, message_id=message_id
            )
        except Exception:
            pass  # one missing/deleted source message shouldn't block the rest


@router.callback_query(F.data == "speaking_recent:multilevel")
async def cb_speaking_recent_multilevel(callback: CallbackQuery, session: AsyncSession):
    section = Section.speaking_recent
    if not await is_section_unlocked(session, callback.from_user.id, section):
        await callback.answer()
        await show_locked_section(callback.message, session, section)
        return

    await callback.answer()
    await callback.message.answer(SPEAKING_RECENT_MULTILEVEL_COMING_SOON)


@router.callback_query(F.data == "more:writing_ai_check")
async def cb_writing_ai_check(callback: CallbackQuery, session: AsyncSession):
    section = Section.writing_ai_check
    if not await is_section_unlocked(session, callback.from_user.id, section):
        await callback.answer()
        await show_locked_section(callback.message, session, section)
        return

    await callback.answer()
    await callback.message.answer(WRITING_AI_CHECK_COMING_SOON)
