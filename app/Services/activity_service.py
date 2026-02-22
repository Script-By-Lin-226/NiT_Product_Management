from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request

from app.Services.admin_service import is_admin_user


def get_actor_details(request: Request | None) -> tuple[str, str]:
    user = getattr(request.state, "user", None) if request is not None else None
    if user is None:
        return ("System", "system")

    actor_name = user.username or user.email or f"user-{user.id}"
    actor_class = "admin" if is_admin_user(user) else "user"
    return (actor_name, actor_class)


def classify_action(change_amount: int) -> str:
    if change_amount > 0:
        return "input"
    if change_amount < 0:
        return "take"
    return "neutral"


def serialize_activity_log(
    *,
    product_name: str,
    change_amount: int,
    created_at: datetime | None,
    actor_name: str | None,
    actor_class: str | None,
    given_to: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    date_iso = created_at.isoformat() if created_at is not None else None
    action = classify_action(int(change_amount))
    resolved_actor_name = (actor_name or "").strip() or "Unknown"
    resolved_actor_class = (actor_class or "").strip() or action

    return {
        "product_name": product_name,
        "change_amount": int(change_amount),
        "name": resolved_actor_name,
        "class": resolved_actor_class,
        "given_to": (given_to or "").strip() or None,
        "department": (department or "").strip() or None,
        "action": action,
        "date": date_iso,
        "created_at": date_iso,
    }
