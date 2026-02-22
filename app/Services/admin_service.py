from fastapi import HTTPException, Request, status

from app.Model.datamodels import User
from app.config.configuration import settings


def _normalized_admin_emails() -> set[str]:
    entries = [entry.strip().lower() for entry in settings.Admin_Emails.split(",")]
    return {entry for entry in entries if entry}


def is_admin_user(user: User | None) -> bool:
    if user is None:
        return False
    return user.email.strip().lower() in _normalized_admin_emails()


def require_admin(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )
    if not is_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
