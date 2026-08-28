from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from admin.deps import get_session, templates
from common.db.models import GATED_SECTIONS, Referral, Section, SectionUnlock, User

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)):
    total_users = await session.scalar(select(func.count()).select_from(User).where(User.telegram_id > 0))
    verified_users = await session.scalar(
        select(func.count()).select_from(User).where(User.telegram_id > 0, User.is_verified_member.is_(True))
    )
    total_valid_referrals = await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.is_valid.is_(True))
    )

    section_counts = {}
    for s in GATED_SECTIONS:
        c = await session.scalar(
            select(func.count()).select_from(SectionUnlock).where(
                SectionUnlock.section == s, SectionUnlock.is_active.is_(True)
            )
        )
        section_counts[s.display_name] = c or 0

    verified_zero_referrals = await session.scalar(
        select(func.count()).select_from(User).where(
            User.telegram_id > 0,
            User.is_verified_member.is_(True),
            ~User.telegram_id.in_(select(Referral.referrer_id).where(Referral.is_valid.is_(True))),
        )
    )
    unverified_count = (total_users or 0) - (verified_users or 0)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "admin": admin,
            "total_users": total_users or 0,
            "verified_users": verified_users or 0,
            "unverified_count": unverified_count,
            "total_valid_referrals": total_valid_referrals or 0,
            "section_counts": section_counts,
            "verified_zero_referrals": verified_zero_referrals or 0,
        },
    )
