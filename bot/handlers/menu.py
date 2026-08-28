from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.reply import BTN_MENU
from bot.services.menu_render import send_main_menu

router = Router(name="menu")

MENU_TRIGGERS = (BTN_MENU, "Asosiy menyu", "/menu")


@router.message(F.text.in_(MENU_TRIGGERS))
async def show_menu(message: Message, session: AsyncSession):
    await send_main_menu(message, session, message.from_user.id, message.from_user.full_name or "do'stim")


@router.callback_query(F.data == "menu")
async def cb_show_menu(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    await send_main_menu(callback.message, session, callback.from_user.id, callback.from_user.full_name or "do'stim")
