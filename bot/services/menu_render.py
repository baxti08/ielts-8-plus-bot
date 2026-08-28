from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards.reply import main_menu_keyboard
from common.referral_logic import active_unlocked_sections


async def send_main_menu(target: Message, session: AsyncSession, user_id: int, profile_name: str) -> None:
    unlocked = await active_unlocked_sections(session, user_id)
    unlocked_keys = {s.value for s in unlocked}
    await target.answer(
        texts.main_menu(profile_name),
        reply_markup=main_menu_keyboard(unlocked_keys),
    )
