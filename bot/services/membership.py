import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from common.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

MEMBER_STATUSES = {"member", "administrator", "creator"}
# "restricted" can still count as a member in Telegram's model, but for a
# subscription gate we only trust the unambiguous "still in the channel" states.


async def is_member_of(bot: Bot, chat_id, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in MEMBER_STATUSES
    except TelegramBadRequest as e:
        # e.g. user never interacted with the channel, or channel/user not found
        logger.warning("get_chat_member failed for chat=%s user=%s: %s", chat_id, user_id, e)
        return False


async def check_all_required(bot: Bot, user_id: int) -> dict:
    """Returns {channel_username: bool_is_member} for all 4 gate channels."""
    results = {}
    for ch in settings.required_channels:
        results[ch["username"]] = await is_member_of(bot, ch["chat_id"], user_id)
    return results


async def is_fully_verified(bot: Bot, user_id: int) -> bool:
    results = await check_all_required(bot, user_id)
    return all(results.values())


def missing_channels(results: dict) -> list:
    channels_by_username = {c["username"]: c for c in settings.required_channels}
    return [channels_by_username[u] for u, ok in results.items() if not ok]
