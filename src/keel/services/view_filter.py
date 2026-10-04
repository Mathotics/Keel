"""Shared board and calendar filters. Choices live in the page address."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from keel.domain.enums import (
    IssuePriority,
    IssueStatus,
    IssueType,
    priorities_in_rank_order,
    statuses_in_workflow_order,
    types_in_hierarchy_order,
)
from keel.services import lookup as lookup_service
from keel.services.issues import IssueFilters
from keel.services.lookup import USER_MESSAGE

NONE_LABEL = "None"


@dataclass(frozen=True)
class Chip:
    param: str
    value: str
    label: str
    remove_href: str


@dataclass(frozen=True)
class ViewFilter:
    """What the bar shows, and the issue query that matches it."""

    types: tuple[IssueType, ...]
    statuses: tuple[IssueStatus, ...]
    priorities: tuple[IssuePriority, ...]
    sprint_ids: frozenset[int]
    unscheduled: bool
    label_chips: tuple[Chip, ...]
    assignee_chips: tuple[Chip, ...]
    reporter_chips: tuple[Chip, ...]
    project_chips: tuple[Chip, ...]
    label_draft: str
    assignee_draft: str
    reporter_draft: str
    project_draft: str
    fields: tuple[tuple[str, str], ...]
    query: str
    error: str | None
    criteria: IssueFilters


@dataclass(frozen=True)
class _Pending:
    param: str
    value: str
    label: str


def load(
    session: Session,
    *,
    base: str,
    submitted: bool,
    types: Sequence[str] = (),
    statuses: Sequence[str] = (),
    priorities: Sequence[str] = (),
    sprints: Sequence[str] = (),
    labels: Sequence[str] = (),
    assignees: Sequence[str] = (),
    reporters: Sequence[str] = (),
    projects: Sequence[str] = (),
    label_add: str | None = None,
    assignee_add: str | None = None,
    reporter_add: str | None = None,
    project_add: str | None = None,
    include_projects: bool = False,
    extra: Sequence[tuple[str, str]] = (),
) -> ViewFilter:
    """Read one page address into checkbox state, chips, and an issue query."""
    error: str | None = None
    type_tokens = _tokens(types)
    types_applied = submitted or bool(type_tokens)
    parsed_types = _enums(type_tokens, IssueType)
    shown_types = parsed_types if types_applied else types_in_hierarchy_order()

    status_values = _enums(statuses, IssueStatus)
    priority_values = _enums(priorities, IssuePriority)
    sprint_ids, unscheduled = _sprints(sprints)

    label_chips, label_names, unlabeled, label_error, label_draft = _labels(
        session,
        [*_tokens(labels), *_draft(label_add)],
        label_add,
    )
    assignee_chips, assignee_ids, unassigned, assignee_error, assignee_draft = _people(
        session,
        [*_tokens(assignees), *_draft(assignee_add)],
        assignee_add,
        allow_unassigned=True,
    )
    reporter_chips, reporter_ids, reporter_none, reporter_error, reporter_draft = (
        _reporters(
            session,
            [*_tokens(reporters), *_draft(reporter_add)],
            reporter_add,
        )
    )
    if include_projects:
        project_chips, project_ids, project_error, project_draft = _projects(
            session,
            [*_tokens(projects), *_draft(project_add)],
            project_add,
        )
    else:
        project_chips = ()
        project_ids = []
        project_error = None
        project_draft = ""

    error = label_error or assignee_error or reporter_error or project_error

    pairs: list[tuple[str, str]] = []
    if types_applied:
        pairs.append(("filters", "1"))
        for issue_type in shown_types:
            pairs.append(("type", issue_type.value))
    for status in status_values:
        pairs.append(("status", status.value))
    for priority in priority_values:
        pairs.append(("priority", priority.value))
    if unscheduled:
        pairs.append(("sprint", "unscheduled"))
    for sprint_id in sprint_ids:
        pairs.append(("sprint", str(sprint_id)))
    for chip in (
        *label_chips,
        *assignee_chips,
        *reporter_chips,
        *project_chips,
    ):
        pairs.append((chip.param, chip.value))

    def href(drop: tuple[str, str]) -> str:
        return _href(base, pairs, extra, drop)

    def finish(group: tuple[_Pending, ...]) -> tuple[Chip, ...]:
        return tuple(
            Chip(
                param=chip.param,
                value=chip.value,
                label=chip.label,
                remove_href=href((chip.param, chip.value)),
            )
            for chip in group
        )

    label_done = finish(label_chips)
    assignee_done = finish(assignee_chips)
    reporter_done = finish(reporter_chips)
    project_done = finish(project_chips)
    has_labels = bool(label_names) or unlabeled
    has_people = bool(assignee_ids) or unassigned
    has_reporters = bool(reporter_ids) or reporter_none
    has_sprints = unscheduled or bool(sprint_ids)
    return ViewFilter(
        types=shown_types,
        statuses=status_values,
        priorities=priority_values,
        sprint_ids=frozenset(sprint_ids),
        unscheduled=unscheduled,
        label_chips=label_done,
        assignee_chips=assignee_done,
        reporter_chips=reporter_done,
        project_chips=project_done,
        label_draft=label_draft,
        assignee_draft=assignee_draft,
        reporter_draft=reporter_draft,
        project_draft=project_draft,
        fields=tuple(pairs),
        query=urlencode(pairs),
        error=error,
        criteria=IssueFilters(
            types=shown_types if types_applied else (),
            require_type=types_applied,
            statuses=status_values,
            priorities=priority_values,
            assignee_any=has_people,
            assignee_ids=tuple(assignee_ids),
            unassigned=unassigned,
            sprint_any=has_sprints,
            sprint_ids=tuple(sprint_ids),
            unscheduled=unscheduled,
            label_any=has_labels,
            labels=tuple(label_names),
            unlabeled=unlabeled,
            reporter_any=has_reporters,
            reporter_ids=tuple(reporter_ids),
            reporter_none=reporter_none,
            project_ids=tuple(project_ids),
        ),
    )


def _failed(failed: str, item: str, draft: str | None) -> str:
    if failed:
        return failed
    if draft and item == draft.strip():
        return draft.strip()
    return item


def _tokens(raw: Sequence[str]) -> list[str]:
    return [item.strip() for item in raw if item and item.strip()]


def _draft(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return []
    return [raw.strip()]


def _enums[E: Enum](raw: Sequence[str], kind: type[E]) -> tuple[E, ...]:
    found: list[E] = []
    seen: set[E] = set()
    for item in _tokens(raw):
        try:
            value = kind(item)
        except ValueError:
            continue
        if value in seen:
            continue
        seen.add(value)
        found.append(value)
    return tuple(found)


def _sprints(raw: Sequence[str]) -> tuple[list[int], bool]:
    ids: list[int] = []
    seen: set[int] = set()
    unscheduled = False
    for item in _tokens(raw):
        if item == "unscheduled":
            unscheduled = True
            continue
        if not item.isdigit():
            continue
        sprint_id = int(item)
        if sprint_id in seen:
            continue
        seen.add(sprint_id)
        ids.append(sprint_id)
    return ids, unscheduled


def _labels(
    session: Session,
    raw: Sequence[str],
    draft: str | None,
) -> tuple[tuple[_Pending, ...], list[str], bool, str | None, str]:
    chips: list[_Pending] = []
    names: list[str] = []
    seen: set[str] = set()
    unlabeled = False
    error: str | None = None
    failed = ""
    for item in raw:
        name, is_unlabeled, message = lookup_service.interpret_board_label(
            session,
            item,
        )
        if message:
            error = error or message
            failed = _failed(failed, item, draft)
            continue
        if is_unlabeled:
            if unlabeled:
                continue
            unlabeled = True
            chips.append(_Pending("label", lookup_service.UNLABELED, "Unlabeled"))
            continue
        if name is None or name in seen:
            continue
        seen.add(name)
        names.append(name)
        chips.append(_Pending("label", name, name))
    return tuple(chips), names, unlabeled, error, failed


def _people(
    session: Session,
    raw: Sequence[str],
    draft: str | None,
    *,
    allow_unassigned: bool,
) -> tuple[tuple[_Pending, ...], list[int], bool, str | None, str]:
    chips: list[_Pending] = []
    ids: list[int] = []
    seen: set[int] = set()
    unassigned = False
    error: str | None = None
    failed = ""
    for item in raw:
        user_id, is_unassigned, shown, message = (
            lookup_service.interpret_board_assignee(
                session,
                item,
            )
        )
        if message:
            error = error or message
            failed = _failed(failed, item, draft)
            continue
        if is_unassigned:
            if not allow_unassigned:
                error = error or USER_MESSAGE
                failed = _failed(failed, item, draft)
                continue
            if unassigned:
                continue
            unassigned = True
            chips.append(_Pending("assignee", shown, shown))
            continue
        if user_id is None or user_id in seen:
            continue
        seen.add(user_id)
        ids.append(user_id)
        chips.append(_Pending("assignee", shown, shown))
    return tuple(chips), ids, unassigned, error, failed


def _reporters(
    session: Session,
    raw: Sequence[str],
    draft: str | None,
) -> tuple[tuple[_Pending, ...], list[int], bool, str | None, str]:
    chips: list[_Pending] = []
    ids: list[int] = []
    seen: set[int] = set()
    none = False
    people: list[str] = []
    for item in raw:
        if item.casefold() == NONE_LABEL.casefold():
            if none:
                continue
            none = True
            chips.append(_Pending("reporter", NONE_LABEL, NONE_LABEL))
            continue
        people.append(item)
    found, found_ids, _unassigned, message, failed = _people(
        session,
        people,
        draft,
        allow_unassigned=False,
    )
    for chip, user_id in zip(found, found_ids, strict=True):
        if user_id in seen:
            continue
        seen.add(user_id)
        ids.append(user_id)
        chips.append(_Pending("reporter", chip.value, chip.label))
    return tuple(chips), ids, none, message, failed


def _projects(
    session: Session,
    raw: Sequence[str],
    draft: str | None,
) -> tuple[tuple[_Pending, ...], list[int], str | None, str]:
    chips: list[_Pending] = []
    ids: list[int] = []
    seen: set[int] = set()
    error: str | None = None
    failed = ""
    for item in raw:
        chosen, shown, message = lookup_service.interpret_project(session, item)
        if message or chosen is None:
            error = error or message or lookup_service.PROJECT_MESSAGE
            failed = _failed(failed, item, draft)
            continue
        if chosen.id in seen:
            continue
        seen.add(chosen.id)
        ids.append(chosen.id)
        chips.append(_Pending("project", shown, shown))
    return tuple(chips), ids, error, failed


def _href(
    base: str,
    pairs: Sequence[tuple[str, str]],
    extra: Sequence[tuple[str, str]],
    drop: tuple[str, str],
) -> str:
    kept: list[tuple[str, str]] = []
    pending: tuple[str, str] | None = drop
    for item in (*pairs, *extra):
        if pending is not None and item == pending:
            pending = None
            continue
        kept.append(item)
    if not kept:
        return base
    return f"{base}?{urlencode(kept)}"


def status_choices() -> tuple[IssueStatus, ...]:
    return statuses_in_workflow_order()


def priority_choices() -> tuple[IssuePriority, ...]:
    return priorities_in_rank_order()
