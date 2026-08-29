from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from admin.deps import get_session, templates
from common.db.models import Referral, User

router = APIRouter(prefix="/referrals")


@router.get("")
async def list_referrals(
    request: Request, q: str = "", session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)
):
    """
    One row per referral relationship: who invited whom, whether it's
    currently valid (counts toward the 3/3 progress), and which section (if
    any) it helped unlock. Search matches either side -- referrer or
    referred -- by telegram id, username, or name.
    """
    LIMIT = 300
    Referrer = aliased(User)
    Referred = aliased(User)

    stmt = (
        select(Referral, Referrer, Referred)
        .join(Referrer, Referral.referrer_id == Referrer.telegram_id)
        .join(Referred, Referral.referred_id == Referred.telegram_id)
    )

    if q:
        if q.isdigit() or (q.startswith("-") and q[1:].isdigit()):
            qid = int(q)
            stmt = stmt.where(or_(Referral.referrer_id == qid, Referral.referred_id == qid))
        else:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Referrer.username.ilike(like),
                    Referrer.full_name.ilike(like),
                    Referred.username.ilike(like),
                    Referred.full_name.ilike(like),
                )
            )

    stmt = stmt.order_by(Referral.created_at.desc()).limit(LIMIT)
    rows = (await session.execute(stmt)).all()

    total_referrals = await session.scalar(select(func.count()).select_from(Referral))
    total_valid = await session.scalar(select(func.count()).select_from(Referral).where(Referral.is_valid.is_(True)))

    return templates.TemplateResponse(
        "referrals.html",
        {
            "request": request,
            "admin": admin,
            "q": q,
            "rows": rows,
            "total_referrals": total_referrals or 0,
            "total_valid": total_valid or 0,
            "showing_capped": not q and (total_referrals or 0) > LIMIT,
            "limit": LIMIT,
        },
    )
