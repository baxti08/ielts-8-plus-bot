from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from admin.deps import get_session, templates
from common.db.models import Referral, User

router = APIRouter(prefix="/leaderboard")

LIMIT = 100


@router.get("")
async def leaderboard(request: Request, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)):
    """
    Ranks users by their VALID referral count (permanent once earned -- see
    common/referral_logic.py). Ties broken by earliest activity (join date)
    so the ranking stays stable rather than shuffling on refresh.
    """
    valid_count = func.count(Referral.id).label("valid_count")
    stmt = (
        select(User, valid_count)
        .join(Referral, Referral.referrer_id == User.telegram_id)
        .where(Referral.is_valid.is_(True))
        .group_by(User.telegram_id)
        .order_by(valid_count.desc(), User.joined_at.asc())
        .limit(LIMIT)
    )
    rows = (await session.execute(stmt)).all()

    return templates.TemplateResponse(
        "leaderboard.html",
        {"request": request, "admin": admin, "rows": rows, "limit": LIMIT},
    )
