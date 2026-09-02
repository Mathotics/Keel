from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.db.session import get_session
from keel.domain.duration import format_minutes
from keel.domain.enums import label
from keel.paths import copyright_notice, templates_dir
from keel.services import users as user_service
from keel.services.identity import USER_COOKIE, USER_HEADER, resolve_current_user
from keel.version import package_version
from keel.web.markdown import render_markdown
from keel.web.nav import NAV_COOKIE, links_for, parse_order

__all__ = [
    "USER_COOKIE",
    "USER_HEADER",
    "Chrome",
    "ChromeDep",
    "SessionDep",
    "get_chrome",
    "get_templates",
    "page_context",
    "resolve_current_user",
]


@lru_cache
def get_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(templates_dir()))
    templates.env.filters["label"] = label
    templates.env.filters["when"] = format_when
    templates.env.filters["datetime_local"] = datetime_local
    templates.env.filters["day"] = format_day
    templates.env.filters["duration"] = format_duration
    templates.env.filters["markdown"] = render_markdown
    return templates


def format_duration(value: int | None) -> str:
    """Shorthand effort for templates; unset stays blank."""
    if value is None:
        return ""
    return format_minutes(value)


def format_when(value: datetime | None) -> str:
    """UTC timestamps as they appear on issue pages."""
    if value is None:
        return "None"
    return _as_naive_utc(value).strftime("%Y-%m-%d %H:%M UTC")


def datetime_local(value: datetime | None) -> str:
    """Value for an HTML datetime-local input."""
    if value is None:
        return ""
    return _as_naive_utc(value).strftime("%Y-%m-%dT%H:%M")


def format_day(value: date | datetime | None) -> str:
    """Calendar dates as they appear on sprint pages."""
    if value is None:
        return "None"
    if isinstance(value, datetime):
        return _as_naive_utc(value).date().isoformat()
    return value.isoformat()


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


@dataclass(frozen=True)
class Chrome:
    """What the shared bar and footer need on every page."""

    users: Sequence[User]
    current_user: User | None


def get_chrome(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Chrome:
    return Chrome(
        users=user_service.list_users(session),
        current_user=resolve_current_user(
            session,
            header=request.headers.get(USER_HEADER),
            cookie=request.cookies.get(USER_COOKIE),
            configured=request.app.state.settings.default_user,
        ),
    )


ChromeDep = Annotated[Chrome, Depends(get_chrome)]
SessionDep = Annotated[Session, Depends(get_session)]


def page_context(request: Request, chrome: Chrome, **extra: Any) -> dict[str, Any]:
    project = extra.get("project")
    key = getattr(project, "key", None)
    project_key = key if isinstance(key, str) else None
    nav_items = links_for(parse_order(request.cookies.get(NAV_COOKIE)), project_key)
    context: dict[str, Any] = {
        "request": request,
        "version": package_version(),
        "copyright_notice": copyright_notice(),
        "users": chrome.users,
        "current_user": chrome.current_user,
        "nav_items": nav_items,
        "nav_keys": ",".join(item.key for item in nav_items),
        **extra,
    }
    context.setdefault("find_query", "")
    return context
