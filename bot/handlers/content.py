from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.referral import show_locked_section
from bot.keyboards.inline import DAYS_PER_PAGE, content_day_grid
from bot.keyboards.reply import SECTION_BUTTON_MAP
from bot.services.content import deliver_bundle, deliver_day
from common.db.models import DAYS_PER_SECTION, Section
from common.referral_logic import is_section_unlocked

router = Router(name="content")

SECTION_MENU_INTRO = {
    Section.reading: "🗂️ <b>IELTS Reading</b> — kerakli kunni tanlang:",
    Section.listening: "🎧 <b>IELTS Listening</b> — kerakli kunni tanlang:",
    Section.speaking: "🗣️ <b>IELTS Speaking</b> — kerakli kunni tanlang:",
    Section.writing: "✍️ <b>IELTS Writing</b> — kerakli kunni tanlang:",
    Section.multilevel: "🔝 <b>Multi-Level darslari</b> — kerakli kunni tanlang:",
}


@router.message(F.text.in_(SECTION_BUTTON_MAP.keys()))
async def open_section(message: Message, session: AsyncSession):
    section = Section(SECTION_BUTTON_MAP[message.text])

    if section.is_gated and not await is_section_unlocked(session, message.from_user.id, section):
        await show_locked_section(message, session, section)
        return

    await message.answer(SECTION_MENU_INTRO[section], reply_markup=content_day_grid(section, 0))


@router.callback_query(F.data.startswith("page:"))
async def cb_page(callback: CallbackQuery, session: AsyncSession):
    _, section_value, page = callback.data.split(":")
    section = Section(section_value)
    page = int(page)

    if section.is_gated and not await is_section_unlocked(session, callback.from_user.id, section):
        await callback.answer("Bu bo'lim hozircha yopiq.", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=content_day_grid(section, page))
    except Exception:
        await callback.message.answer(SECTION_MENU_INTRO[section], reply_markup=content_day_grid(section, page))


@router.callback_query(F.data.startswith("day:"))
async def cb_day(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    _, section_value, day = callback.data.split(":")
    section = Section(section_value)
    day = int(day)
    user_id = callback.from_user.id

    if section.is_gated and not await is_section_unlocked(session, user_id, section):
        await callback.answer("Bu bo'lim hozircha yopiq.", show_alert=True)
        return

    await callback.answer("⏳ Yuborilmoqda...")
    delivered = await deliver_day(bot, user_id, session, section, day)
    if not delivered:
        await bot.send_message(user_id, f"❗️ {day}-kun uchun material hali yuklanmagan. Birozdan so'ng urinib ko'ring.")


@router.callback_query(F.data.startswith("bundle:"))
async def cb_bundle(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    _, section_value, page = callback.data.split(":")
    section = Section(section_value)
    page = int(page)
    user_id = callback.from_user.id

    if section.is_gated and not await is_section_unlocked(session, user_id, section):
        await callback.answer("Bu bo'lim hozircha yopiq.", show_alert=True)
        return

    total_days = DAYS_PER_SECTION[section]
    start = page * DAYS_PER_PAGE + 1
    end = min(start + DAYS_PER_PAGE - 1, total_days)

    await callback.answer("⏳ Yuborilmoqda...")
    count = await deliver_bundle(bot, user_id, session, section, start, end)
    await bot.send_message(user_id, f"✅ {start}-{end} kunlar yuborildi ({count} ta dars).")
