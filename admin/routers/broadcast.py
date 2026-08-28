from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from common.broadcast_sender import run_broadcast
from admin.deps import get_session, templates
from common.broadcast_segments import SEGMENTS, get_target_user_ids
from common.db.models import BroadcastLog

router = APIRouter(prefix="/broadcast")


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


@router.post("/send")
async def send_broadcast(
    background_tasks: BackgroundTasks,
    segment: str = Form(...),
    message_text: str = Form(...),
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

    target_ids = await get_target_user_ids(session, segment)

    log = BroadcastLog(
        segment=segment,
        message_text=message_text,
        total_targets=len(target_ids),
        created_by=admin,
        status="pending",
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    background_tasks.add_task(run_broadcast, log.id, target_ids, message_text)

    return RedirectResponse(url="/broadcast", status_code=303)
