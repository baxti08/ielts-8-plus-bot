from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from admin.deps import get_session, templates
from admin.direct_message import send_direct_message
from common.admin_ops import manual_add_points, manual_revoke_points
from common.db.models import AdminAction, Referral, User
from common.referral_logic import active_unlocked_sections, referral_progress

router = APIRouter(prefix="/users")


@router.get("")
async def search_users(
    request: Request, q: str = "", session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)
):
    LIMIT = 200
    stmt = select(User).where(User.telegram_id > 0)
    if q:
        if q.isdigit() or (q.startswith("-") and q[1:].isdigit()):
            stmt = stmt.where(User.telegram_id == int(q))
        else:
            stmt = stmt.where(or_(User.username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    stmt = stmt.order_by(User.joined_at.desc()).limit(LIMIT)
    results = (await session.scalars(stmt)).all()

    total_users = await session.scalar(select(func.count()).select_from(User).where(User.telegram_id > 0))

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "admin": admin,
            "q": q,
            "results": results,
            "total_users": total_users or 0,
            "showing_capped": not q and (total_users or 0) > LIMIT,
            "limit": LIMIT,
        },
    )


@router.get("/{user_id}")
async def user_detail(
    user_id: int, request: Request, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)
):
    user = await session.get(User, user_id)
    if not user:
        return RedirectResponse(url="/users", status_code=303)

    progress = await referral_progress(session, user_id)
    unlocked = await active_unlocked_sections(session, user_id)
    sent_referrals = (
        await session.scalars(
            select(Referral).where(Referral.referrer_id == user_id).order_by(Referral.created_at.desc())
        )
    ).all()

    return templates.TemplateResponse(
        "user_detail.html",
        {
            "request": request,
            "admin": admin,
            "user": user,
            "progress": progress,
            "unlocked": unlocked,
            "sent_referrals": sent_referrals,
            "message_result": request.query_params.get("message_result"),
        },
    )


@router.post("/{user_id}/adjust")
async def adjust_points(
    user_id: int,
    action: str = Form(...),
    count: int = Form(...),
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
):
    if count > 0:
        if action == "add":
            await manual_add_points(session, admin, user_id, count)
        elif action == "revoke":
            await manual_revoke_points(session, admin, user_id, count)
        await session.commit()
    return RedirectResponse(url=f"/users/{user_id}", status_code=303)


@router.post("/{user_id}/message")
async def message_user(
    user_id: int,
    text: str = Form(...),
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
):
    success, error = await send_direct_message(user_id, text)

    session.add(
        AdminAction(
            admin_username=admin,
            action_type="direct_message",
            target_user_id=user_id,
            old_value=None,
            new_value=text if success else f"FAILED: {error}",
        )
    )
    await session.commit()

    result = "sent" if success else f"failed:{error}"
    return RedirectResponse(url=f"/users/{user_id}?message_result={result}", status_code=303)
