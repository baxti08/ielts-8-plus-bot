"""
Admin-only bot command: /broadcast. Lets the admin (settings.admin_id_list)
pick a segment and compose a broadcast message directly in Telegram, without
opening the web admin panel.

Runs the same common/broadcast_sender.py used by the web panel, launched as
a background asyncio task inside THIS process (the bot service) rather than
the admin service. This is safe -- not because it's a separate process (it
isn't, this time), but because the send loop is pure async I/O (network
calls + brief DB writes, nothing CPU-bound) that yields control back to the
event loop on every await, so it doesn't block concurrent webhook handling;
and run_broadcast already catches every exception internally rather than
letting one propagate and take down the process. The same "one broadcast at
a time" guard as the web panel applies here too, checked against the same
BroadcastLog table -- so triggering it from the bot and from the web panel
can't race each other.
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.broadcast_segments import SEGMENTS, get_target_user_ids, parse_exclude_ids
from common.broadcast_sender import run_broadcast
from common.config import get_settings
from common.db.models import BroadcastLog

router = Router(name="admin_broadcast")
logger = logging.getLogger("bot.admin_broadcast")
settings = get_settings()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_id_list


class BroadcastStates(StatesGroup):
    choosing_segment = State()
    typing_include_ids = State()
    typing_excludes = State()
    typing_message = State()
    confirming = State()


def _segment_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admbc_seg:{key}")]
        for key, label in SEGMENTS.items()
    ]
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admbc_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Yuborish", callback_data="admbc_confirm")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admbc_cancel")],
        ]
    )


LIVE_UPDATE_INTERVAL = 4  # seconds between live progress edits

_STATUS_LABELS = {
    "pending": "boshlanmoqda...",
    "running": "yuborilmoqda...",
    "done": "yakunlandi ✅",
    "failed": "xato ❌",
}


def _format_status(log: BroadcastLog) -> str:
    processed = log.sent_count + log.failed_count
    pct = (processed / log.total_targets * 100) if log.total_targets else 0
    return (
        f"📤 Broadcast #{log.id} — {SEGMENTS.get(log.segment, log.segment)}\n"
        f"Holat: {_STATUS_LABELS.get(log.status, log.status)}\n\n"
        f"✅ Yuborildi: {log.sent_count}\n"
        f"❌ Xato: {log.failed_count}\n"
        f"📊 Jami: {processed}/{log.total_targets} ({pct:.0f}%)"
    )


async def _live_status_loop(bot: Bot, chat_id: int, message_id: int, broadcast_id: int):
    """Edits the given message every LIVE_UPDATE_INTERVAL seconds with fresh
    progress, until the broadcast finishes (done/failed) or the row vanishes."""
    from common.db.engine import SessionLocal

    last_text = None
    while True:
        await asyncio.sleep(LIVE_UPDATE_INTERVAL)
        async with SessionLocal() as session:
            log = await session.get(BroadcastLog, broadcast_id)
        if log is None:
            break
        text = _format_status(log)
        if text != last_text:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
                last_text = text
            except Exception:
                pass  # e.g. "message is not modified", or message/chat gone -- just skip this tick
        if log.status in ("done", "failed"):
            break


@router.message(Command("broadcast"), F.from_user.id.in_(settings.admin_id_list))
async def cmd_broadcast(message: Message, state: FSMContext):
    running = await _get_running_broadcast(message)
    if running:
        await message.answer(
            f"⚠️ Hozir allaqachon #{running.id} ({running.segment}) ishlamoqda — "
            f"{running.sent_count}/{running.total_targets}. U tugagunicha yangisini boshlab bo'lmaydi."
        )
        return
    await state.set_state(BroadcastStates.choosing_segment)
    await message.answer("📤 Kimlarga xabar yuborilsin?", reply_markup=_segment_keyboard())


async def _get_running_broadcast(message: Message) -> BroadcastLog | None:
    from common.db.engine import SessionLocal

    async with SessionLocal() as session:
        return await session.scalar(
            select(BroadcastLog).where(BroadcastLog.status.in_(["pending", "running"])).limit(1)
        )


@router.callback_query(StateFilter(BroadcastStates.choosing_segment), F.data.startswith("admbc_seg:"))
async def cb_choose_segment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    segment = callback.data.split(":", 1)[1]
    await state.update_data(segment=segment)
    await callback.answer()

    if segment == "custom_ids":
        await state.set_state(BroadcastStates.typing_include_ids)
        await callback.message.edit_text(
            "🎯 Faqat qaysi foydalanuvchilarga yuborilsin? Telegram ID'larini vergul bilan kiriting "
            "(masalan: 806124512, 431228526):"
        )
        return

    await state.set_state(BroadcastStates.typing_excludes)
    await callback.message.edit_text(
        f"👥 Tanlandi: <b>{SEGMENTS[segment]}</b>\n\n"
        "Istisno qilinadigan foydalanuvchilar bormi? Telegram ID'larini vergul bilan kiriting "
        "(masalan: 806124512, 431228526), yoki hech kimni istisno qilmaslik uchun \"yo'q\" deb yozing:"
    )


@router.message(StateFilter(BroadcastStates.typing_include_ids), F.from_user.id.in_(settings.admin_id_list))
async def receive_include_ids(message: Message, state: FSMContext, session: AsyncSession):
    include_ids = parse_exclude_ids(message.text or "")
    if not include_ids:
        await message.answer(
            "⚠️ Hech qanday to'g'ri Telegram ID topilmadi. Iltimos, ID'larni vergul bilan qayta kiriting:"
        )
        return

    target_ids = await get_target_user_ids(session, "custom_ids", include_ids=include_ids)
    await state.update_data(include_ids=include_ids, target_count=len(target_ids))
    await state.set_state(BroadcastStates.typing_message)
    await message.answer(
        f"🎯 Tanlandi: <b>Faqat tanlangan ID'lar</b> ({len(target_ids)} ta topildi, {len(include_ids)} ta kiritilgan edi)\n\n"
        "Endi xabar yuboring — matn, rasm, video yoki ovozli xabar bo'lishi mumkin "
        "(HTML formatlash qo'llab-quvvatlanadi):"
    )


@router.message(StateFilter(BroadcastStates.typing_excludes), F.from_user.id.in_(settings.admin_id_list))
async def receive_excludes(message: Message, state: FSMContext, session: AsyncSession):
    exclude_ids = parse_exclude_ids(message.text or "")
    data = await state.get_data()
    target_ids = await get_target_user_ids(session, data["segment"], exclude_ids=exclude_ids)
    await state.update_data(exclude_ids=exclude_ids, target_count=len(target_ids))
    await state.set_state(BroadcastStates.typing_message)

    excluded_note = f"\n🚫 Istisno qilindi: {len(exclude_ids)} ta foydalanuvchi" if exclude_ids else ""
    await message.answer(
        f"👥 Tanlandi: <b>{SEGMENTS[data['segment']]}</b> ({len(target_ids)} ta foydalanuvchi){excluded_note}\n\n"
        "Endi xabar yuboring — matn, rasm, video yoki ovozli xabar bo'lishi mumkin "
        "(HTML formatlash qo'llab-quvvatlanadi):"
    )


def _label_for_message(message: Message) -> str:
    """Short human-readable summary for the confirm screen and history table.
    The actual broadcast never re-reads this -- it copies the real message
    via bot.copy_message using source_chat_id/source_message_id, so this
    works the same whether the admin sent text, a photo, a video, a voice
    note, or a document."""
    if message.text:
        return message.html_text
    caption = message.caption or ""
    if message.photo:
        return caption or "[rasm]"
    if message.video:
        return caption or "[video]"
    if message.voice:
        return caption or "[ovozli xabar]"
    if message.document:
        return caption or "[fayl]"
    if message.audio:
        return caption or "[audio]"
    return caption or "[media]"


@router.message(StateFilter(BroadcastStates.typing_message), F.from_user.id.in_(settings.admin_id_list))
async def receive_broadcast_content(message: Message, state: FSMContext):
    data = await state.get_data()
    label = _label_for_message(message)
    is_text_only = message.content_type == "text"
    await state.update_data(
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
        message_text=label,
        text_only_content=label if is_text_only else None,
    )
    await state.set_state(BroadcastStates.confirming)
    await message.answer(
        f"📋 Tayyor:\n\n"
        f"Kimlarga: <b>{SEGMENTS[data['segment']]}</b> ({data['target_count']} ta)\n\n"
        f"Xabar (yuqorida ko'rsatildi): {label}\n\n"
        "Yuborishni tasdiqlaysizmi?",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(StateFilter(BroadcastStates.confirming), F.data == "admbc_confirm")
async def cb_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    segment = data["segment"]
    message_text = data["message_text"]
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]

    already_running = await session.scalar(
        select(BroadcastLog).where(BroadcastLog.status.in_(["pending", "running"])).limit(1)
    )
    if already_running:
        await callback.answer()
        await callback.message.edit_text("⚠️ Boshqa broadcast allaqachon ishga tushdi. Qayta urinib ko'ring.")
        await state.clear()
        return

    target_ids = await get_target_user_ids(
        session, segment, exclude_ids=data.get("exclude_ids"), include_ids=data.get("include_ids")
    )
    log = BroadcastLog(
        segment=segment,
        message_text=message_text,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        total_targets=len(target_ids),
        created_by=f"bot_admin:{callback.from_user.id}",
        status="pending",
    )
    session.add(log)
    await session.flush()
    log_id = log.id
    await session.commit()

    asyncio.create_task(
        run_broadcast(log_id, target_ids, source_chat_id, source_message_id, data.get("text_only_content"))
    )

    await callback.answer("Boshlandi!")
    placeholder = BroadcastLog(
        id=log_id, segment=segment, status="pending", sent_count=0, failed_count=0, total_targets=len(target_ids)
    )
    await callback.message.edit_text(_format_status(placeholder))
    asyncio.create_task(
        _live_status_loop(bot, callback.message.chat.id, callback.message.message_id, log_id)
    )
    await state.clear()


@router.callback_query(F.data == "admbc_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("❌ Bekor qilindi.")


@router.message(Command("broadcast_status"), F.from_user.id.in_(settings.admin_id_list))
async def cmd_broadcast_status(message: Message, session: AsyncSession, bot: Bot):
    log = await session.scalar(select(BroadcastLog).order_by(BroadcastLog.created_at.desc()).limit(1))
    if not log:
        await message.answer("Hali broadcast yo'q.")
        return
    sent = await message.answer(_format_status(log))
    if log.status in ("pending", "running"):
        asyncio.create_task(_live_status_loop(bot, sent.chat.id, sent.message_id, log.id))
