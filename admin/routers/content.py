from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin
from admin.deps import get_session, templates
from common.config import get_settings
from common.db.models import Content, DAYS_PER_SECTION, Section

router = APIRouter(prefix="/content")
settings = get_settings()


def _parse_ids(raw: str) -> list[int]:
    ids = []
    for part in raw.replace(" ", "").split(","):
        if part:
            ids.append(int(part))
    if not ids:
        raise ValueError("At least one message id is required")
    return ids


@router.get("")
async def list_content(request: Request, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)):
    rows = (await session.scalars(select(Content).order_by(Content.section, Content.day_number))).all()
    by_section: dict[str, list[Content]] = {s.value: [] for s in Section}
    for r in rows:
        by_section[r.section.value].append(r)

    edit_values = None
    edit_section = request.query_params.get("edit_section")
    edit_day = request.query_params.get("edit_day")
    if edit_section and edit_day:
        for r in rows:
            if r.section.value == edit_section and str(r.day_number) == edit_day:
                edit_values = {
                    "section": r.section.value,
                    "day_number": r.day_number,
                    "message_ids": ",".join(str(i) for i in r.message_ids),
                }
                break

    return templates.TemplateResponse(
        "content.html",
        {
            "request": request,
            "admin": admin,
            "by_section": by_section,
            "sections": list(Section),
            "days_per_section": DAYS_PER_SECTION,
            "error": request.query_params.get("error"),
            "edit_values": edit_values,
        },
    )


@router.post("/save")
async def save_content(
    section: str = Form(...),
    day_number: int = Form(...),
    message_ids: str = Form(...),
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
):
    try:
        sec = Section(section)
        ids = _parse_ids(message_ids)
    except ValueError as e:
        return RedirectResponse(url=f"/content?error={e}", status_code=303)

    existing = await session.scalar(
        select(Content).where(Content.section == sec, Content.day_number == day_number)
    )
    channel_id = settings.content_channel_map[sec.value]
    if existing:
        existing.message_ids = ids
        existing.source_channel_id = channel_id
    else:
        session.add(Content(section=sec, day_number=day_number, source_channel_id=channel_id, message_ids=ids))
    await session.commit()
    return RedirectResponse(url="/content", status_code=303)


@router.post("/{content_id}/delete")
async def delete_content(content_id: int, session: AsyncSession = Depends(get_session), admin: str = Depends(require_admin)):
    row = await session.get(Content, content_id)
    if row:
        await session.delete(row)
        await session.commit()
    return RedirectResponse(url="/content", status_code=303)
