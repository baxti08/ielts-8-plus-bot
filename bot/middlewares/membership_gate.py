"""
Blocks any interaction other than /start and the gate_check callback until the
user is verified (DB flag `is_verified_member`, kept fresh by the /start flow,
the "✅ A'zo bo'ldim" button, and chat_member update events -- see
bot/handlers/membership.py and bot/handlers/chat_member.py). This middleware
does NOT call Telegram itself, to keep every other message/callback cheap.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
from bot.keyboards.inline import gate_channels_keyboard
from common.config import get_settings
from common.db.models import User

settings = get_settings()

# Callback/command entry points allowed through even when unverified.
ALLOWED_CALLBACK_PREFIXES = ("gate_check",)
ALLOWED_COMMANDS = ("/start",)


class MembershipGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data["session"]

        if isinstance(event, Message):
            if event.from_user.id in settings.admin_id_list:
                return await handler(event, data)
            text = event.text or ""
            if text.startswith(ALLOWED_COMMANDS):
                return await handler(event, data)
            user_id = event.from_user.id
            user = await session.get(User, user_id)
            if user is None or not user.is_verified_member:
                await event.answer(texts.gate_message(), reply_markup=gate_channels_keyboard(), disable_web_page_preview=True)
                return None
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            if event.from_user.id in settings.admin_id_list:
                return await handler(event, data)
            if event.data and event.data.startswith(ALLOWED_CALLBACK_PREFIXES):
                return await handler(event, data)
            user_id = event.from_user.id
            user = await session.get(User, user_id)
            if user is None or not user.is_verified_member:
                await event.answer("Avval kanallarga a'zo bo'ling.", show_alert=True)
                return None
            return await handler(event, data)

        return await handler(event, data)
