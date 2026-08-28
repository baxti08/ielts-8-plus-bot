import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.models import Content, ContentDelivery, Section

logger = logging.getLogger(__name__)


async def _log_delivery(session: AsyncSession, user_id: int, content: Content) -> None:
    session.add(ContentDelivery(user_id=user_id, section=content.section, day_number=content.day_number))
    await session.flush()


async def get_content(session: AsyncSession, section: Section, day_number: int) -> Content | None:
    return await session.scalar(
        select(Content).where(Content.section == section, Content.day_number == day_number)
    )


async def get_content_range(session: AsyncSession, section: Section, start_day: int, end_day: int) -> list[Content]:
    rows = await session.scalars(
        select(Content)
        .where(Content.section == section, Content.day_number >= start_day, Content.day_number <= end_day)
        .order_by(Content.day_number.asc())
    )
    return list(rows.all())


async def deliver_content(bot: Bot, chat_id: int, content: Content) -> int:
    """copyMessage every message_id for this day, protect_content=True. Returns count sent."""
    sent = 0
    for msg_id in content.message_ids:
        for attempt in range(3):
            try:
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=content.source_channel_id,
                    message_id=msg_id,
                    protect_content=True,
                )
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except TelegramBadRequest as e:
                logger.error("copy_message failed chat=%s src=%s msg=%s: %s", chat_id, content.source_channel_id, msg_id, e)
                break
        await asyncio.sleep(0.05)  # gentle pacing to avoid flood limits
    return sent


async def deliver_day(bot: Bot, chat_id: int, session: AsyncSession, section: Section, day_number: int) -> bool:
    content = await get_content(session, section, day_number)
    if content is None:
        return False
    await deliver_content(bot, chat_id, content)
    await _log_delivery(session, chat_id, content)
    return True


async def deliver_bundle(bot: Bot, chat_id: int, session: AsyncSession, section: Section, start_day: int, end_day: int) -> int:
    items = await get_content_range(session, section, start_day, end_day)
    count = 0
    for c in items:
        await deliver_content(bot, chat_id, c)
        await _log_delivery(session, chat_id, c)
        count += 1
    return count
