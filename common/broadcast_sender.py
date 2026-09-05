"""
Rate-limited broadcast sender. Runs as a FastAPI BackgroundTask inside the
admin process -- entirely separate from the bot's own webhook-handling
process, so a long broadcast run cannot block or crash real-time /start
handling. For a 50k-user broadcast this takes roughly 30 minutes at the
default rate; progress is persisted to BroadcastLog periodically so the
admin dashboard can poll it. If the admin process restarts mid-broadcast,
the run is left in status="running" and does not auto-resume -- re-trigger
manually (kept simple on purpose; a durable job queue is the natural next
step if broadcast volume grows well past this scale).

Resilience notes (why this can't take the bot down):
- Each user send is isolated -- one failure (blocked bot, bad chat, etc.)
  never aborts the batch or the run.
- Telegram flood-control errors (TelegramRetryAfter) are handled by
  sleeping exactly as long as Telegram asks, then continuing -- this is
  graceful backoff, not a crash.
- The whole run is wrapped in try/except; an unexpected error marks the
  BroadcastLog as "failed" and exits cleanly rather than raising into the
  admin process.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest
from aiogram.types import LinkPreviewOptions

from common.config import get_settings
from common.db.engine import SessionLocal
from common.db.models import BroadcastLog

settings = get_settings()
logger = logging.getLogger("admin.broadcast")

RATE_PER_SEC = settings.broadcast_rate_per_sec  # messages/sec, just under Telegram's ~30/sec ceiling
PROGRESS_WRITE_EVERY = 10  # persist progress every N batches (~10s), not every batch -- lighter on the DB at 50k scale


async def run_broadcast(
    broadcast_id: int,
    user_ids: list[int],
    source_chat_id: int,
    source_message_id: int,
    text_only_content: str | None = None,
):
    """
    source_chat_id/source_message_id point at a single already-sent Telegram
    message (text, photo, video, voice, document -- anything) that every
    target user receives a copy of via bot.copy_message. Both the web panel
    and the bot's /broadcast command relay whatever the admin composed to
    BACKUP_ADMIN_CHAT_ID first (see admin/routers/broadcast.py and
    bot/handlers/admin_broadcast.py) to get this source message, so this
    function itself never needs to know or care what type of content it is.

    text_only_content: if the composed message was pure text (no media),
    this holds that exact HTML text, captured at compose time -- the Bot API
    has no way to read an arbitrary message's content back later, so this
    must be passed in rather than looked up. When present, every send uses
    send_message with link previews forced off instead of copy_message,
    since a preview attached to the ORIGINAL message can't be stripped via
    copy_message after the fact (link_preview_options is a property that
    only exists on the send itself, not the resulting message you'd copy).
    """
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        async with SessionLocal() as session:
            log = await session.get(BroadcastLog, broadcast_id)
            log.status = "running"
            log.started_at = datetime.now(timezone.utc)
            await session.commit()

        sent, failed = 0, 0
        for batch_num, i in enumerate(range(0, len(user_ids), RATE_PER_SEC), start=1):
            batch = user_ids[i : i + RATE_PER_SEC]
            batch_start = time.monotonic()

            results = await asyncio.gather(
                *(_send_one(bot, uid, source_chat_id, source_message_id, text_only_content) for uid in batch)
            )
            sent += sum(1 for r in results if r)
            failed += sum(1 for r in results if not r)

            if batch_num % PROGRESS_WRITE_EVERY == 0:
                async with SessionLocal() as session:
                    log = await session.get(BroadcastLog, broadcast_id)
                    log.sent_count = sent
                    log.failed_count = failed
                    await session.commit()

            # Dynamic pacing: only sleep the remainder of the 1-second window,
            # so we hit close to RATE_PER_SEC without ever exceeding it --
            # a batch that itself took 0.4s only sleeps 0.6s, not a flat 1s.
            elapsed = time.monotonic() - batch_start
            await asyncio.sleep(max(0.0, 1.0 - elapsed))

        async with SessionLocal() as session:
            log = await session.get(BroadcastLog, broadcast_id)
            log.status = "done"
            log.sent_count = sent
            log.failed_count = failed
            log.completed_at = datetime.now(timezone.utc)
            await session.commit()
    except Exception:
        logger.exception("Broadcast %s crashed", broadcast_id)
        async with SessionLocal() as session:
            log = await session.get(BroadcastLog, broadcast_id)
            if log:
                log.status = "failed"
                log.completed_at = datetime.now(timezone.utc)
                await session.commit()
    finally:
        await bot.session.close()


async def _send_one(
    bot: Bot, user_id: int, source_chat_id: int, source_message_id: int, text_only_content: str | None = None
) -> bool:
    for attempt in range(2):
        try:
            if text_only_content is not None:
                await bot.send_message(
                    user_id, text_only_content, link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            else:
                await bot.copy_message(chat_id=user_id, from_chat_id=source_chat_id, message_id=source_message_id)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            return False  # user blocked the bot
        except TelegramBadRequest:
            return False
        except Exception:
            logger.exception("Unexpected error sending to %s", user_id)
            return False
    return False
