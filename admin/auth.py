import hmac

from fastapi import Request

from common.config import get_settings

settings = get_settings()

SESSION_KEY = "admin_user"


class RedirectToLogin(Exception):
    pass


def verify_credentials(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password, settings.admin_password
    )


def login_session(request: Request, username: str) -> None:
    request.session[SESSION_KEY] = username


def logout_session(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def require_admin(request: Request) -> str:
    user = request.session.get(SESSION_KEY)
    if not user:
        raise RedirectToLogin()
    return user
