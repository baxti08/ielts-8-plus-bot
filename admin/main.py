from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from admin.auth import RedirectToLogin, login_session, logout_session, verify_credentials
from admin.deps import templates
from admin.routers import broadcast, content, leaderboard, referrals, stats, users
from common.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="IELTS 8+ Bot Admin")
app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key, session_cookie="ielts_admin_session")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.exception_handler(RedirectToLogin)
async def redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_credentials(username, password):
        login_session(request, username)
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Login yoki parol noto'g'ri"})


@app.post("/logout")
async def logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(stats.router)
app.include_router(content.router)
app.include_router(users.router)
app.include_router(referrals.router)
app.include_router(leaderboard.router)
app.include_router(broadcast.router)
