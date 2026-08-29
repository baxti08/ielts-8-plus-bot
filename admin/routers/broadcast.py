from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from common.broadcast_sender import run_broadcast
from admin.deps import get_session, templates
from common.broadcast_segments import SEGMENTS, get_target_user_ids
from common.config import get_settings
from common.db.models import BroadcastLog

router = APIRouter(prefix="/broadcast")
settings = get_settings()


@router.get("")
async def broadcast_form(request: Request, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)):
    logs = (await session.scalars(select(BroadcastLog).order_by(BroadcastLog.created_at.desc()).limit(20))).all()
    running = await session.scalar(
        select(BroadcastLog).where(BroadcastLog.status.in_(["pending", "running"])).limit(1)
    )
    return templates.TemplateResponse(
        "broadcast.html",
        {"request": request, "admin": admin, "segments": SEGMENTS, "logs": logs, "running": running},
    )


async def _relay_to_source_message(
    bot: Bot, message_text: Optional[str], media: Optional[UploadFile]
) -> tuple[int, int, str]:
    """
    Sends whatever the admin composed (text, or an uploaded photo/video/
    voice/document with an optional caption) to BACKUP_ADMIN_CHAT_ID once,
    to create a single real Telegram message. Returns that message's
    (chat_id, message_id) -- run_broadcast then copies THAT message to every
    target via bot.copy_message, which works for any content type. This
    also doubles as a durable "what did we actually send" record in the
    admin's own chat history.

    Returns (source_chat_id, source_message_id, label) where label is a
    short human-readable string for the history table.
    """
    chat_id = settings.backup_admin_chat_id

    if media is not None and media.filename:
        content = await media.read()
        content_type = media.content_type or ""
        input_file = BufferedInputFile(content, filename=media.filename)

        if content_type.startswith("image/"):
            sent = await bot.send_photo(chat_id, input_file, caption=message_text or None)
            label = message_text or "[photo]"
        elif content_type.startswith("video/"):
            sent = await bot.send_video(chat_id, input_file, caption=message_text or None)
            label = message_text or "[video]"
        elif content_type in ("audio/ogg", "audio/opus") or media.filename.endswith(".ogg"):
            sent = await bot.send_voice(chat_id, input_file, caption=message_text or None)
            label = message_text or "[voice]"
        elif content_type.startswith("audio/"):
            sent = await bot.send_audio(chat_id, input_file, caption=message_text or None)
            label = message_text or "[audio]"
        else:
            sent = await bot.send_document(chat_id, input_file, caption=message_text or None)
            label = message_text or "[document]"
    else:
        sent = await bot.send_message(chat_id, message_text)
        label = message_text

    return chat_id, sent.message_id, label


@router.post("/send")
async def send_broadcast(
    background_tasks: BackgroundTasks,
    segment: str = Form(...),
    message_text: str = Form(""),
    media: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
):
    # Guard against accidentally launching a second broadcast while one is
    # still running -- at 50k scale, two concurrent runs would double the
    # send rate against Telegram's per-bot limit for no good reason.
    already_running = await session.scalar(
        select(BroadcastLog).where(BroadcastLog.status.in_(["pending", "running"])).limit(1)
    )
    if already_running:
        return RedirectResponse(url="/broadcast?error=already_running", status_code=303)

    if not message_text and (media is None or not media.filename):
        return RedirectResponse(url="/broadcast?error=empty", status_code=303)

    target_ids = await get_target_user_ids(session, segment)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        source_chat_id, source_message_id, label = await _relay_to_source_message(bot, message_text, media)
    finally:
        await bot.session.close()

    log = BroadcastLog(
        segment=segment,
        message_text=label,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        total_targets=len(target_ids),
        created_by=admin,
        status="pending",
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    background_tasks.add_task(run_broadcast, log.id, target_ids, source_chat_id, source_message_id)

    return RedirectResponse(url="/broadcast", status_code=303)
