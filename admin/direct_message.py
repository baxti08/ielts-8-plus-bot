from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from common.config import get_settings

settings = get_settings()


async def send_direct_message(user_id: int, text: str) -> tuple[bool, str]:
    """Returns (success, error_message_if_any)."""
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot.send_message(user_id, text)
        return True, ""
    except TelegramForbiddenError:
        return False, "Foydalanuvchi botni bloklagan."
    except TelegramBadRequest as e:
        return False, str(e)
    finally:
        await bot.session.close()
