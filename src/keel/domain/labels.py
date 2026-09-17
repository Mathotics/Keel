"""Rules for issue label names. This module imports no database."""

from collections.abc import Sequence
from re import compile as re_compile

from keel.domain.errors import InvalidIssueError

MAX_LABEL_LENGTH = 40
LABEL_PATTERN = re_compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def normalize_label_name(raw: str) -> str:
    """Trim, lowercase, and collapse whitespace to hyphens."""
    cleaned = "-".join(raw.strip().lower().split())
    if not cleaned:
        raise InvalidIssueError("A label needs a name.")
    if len(cleaned) > MAX_LABEL_LENGTH:
        raise InvalidIssueError(
            f"A label name may be at most {MAX_LABEL_LENGTH} characters.",
            limit=MAX_LABEL_LENGTH,
        )
    if not LABEL_PATTERN.fullmatch(cleaned):
        raise InvalidIssueError(
            "Labels use letters, digits, hyphen, and underscore.",
            name=cleaned,
        )
    return cleaned


def parse_label_names(values: Sequence[str] | str) -> tuple[str, ...]:
    """Split a comma-separated string or a list into unique normalized names."""
    parts = values.split(",") if isinstance(values, str) else list(values)
    seen: list[str] = []
    for part in parts:
        if not str(part).strip():
            continue
        name = normalize_label_name(str(part))
        if name not in seen:
            seen.append(name)
    return tuple(seen)
