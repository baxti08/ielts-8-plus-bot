from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.engine import SessionLocal

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
