"""Query parameters for the shared board and calendar filter bar."""

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import Query, Request
from sqlalchemy.orm import Session

from keel.db.models import Sprint
from keel.domain.enums import types_in_hierarchy_order
from keel.services import boards as board_service
from keel.services import sprints as sprint_service
from keel.services import view_filter
from keel.services.view_filter import ViewFilter

DATE_PARAMS = ("view", "month", "week", "day", "year", "month_num", "day_num")


@dataclass(frozen=True)
class FilterRequest:
    submitted: bool
    types: tuple[str, ...]
    statuses: tuple[str, ...]
    priorities: tuple[str, ...]
    sprints: tuple[str, ...]
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    reporters: tuple[str, ...]
    projects: tuple[str, ...]
    label_add: str | None
    assignee_add: str | None
    reporter_add: str | None
    project_add: str | None


def filter_request(
    filters: str | None = None,
    types: list[str] = Query(default=[], alias="type"),
    status: list[str] = Query(default=[]),
    priority: list[str] = Query(default=[]),
    sprint: list[str] = Query(default=[]),
    label: list[str] = Query(default=[]),
    assignee: list[str] = Query(default=[]),
    reporter: list[str] = Query(default=[]),
    project: list[str] = Query(default=[]),
    label_add: str | None = None,
    assignee_add: str | None = None,
    reporter_add: str | None = None,
    project_add: str | None = None,
) -> FilterRequest:
    return FilterRequest(
        submitted=filters == "1",
        types=tuple(types),
        statuses=tuple(status),
        priorities=tuple(priority),
        sprints=tuple(sprint),
        labels=tuple(label),
        assignees=tuple(assignee),
        reporters=tuple(reporter),
        projects=tuple(project),
        label_add=label_add,
        assignee_add=assignee_add,
        reporter_add=reporter_add,
        project_add=project_add,
    )


def date_pairs(request: Request) -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []
    for key in DATE_PARAMS:
        value = request.query_params.get(key)
        if value:
            found.append((key, value))
    return tuple(found)


def layout_pairs(grouping: str | None) -> tuple[tuple[str, str], ...]:
    if grouping == "sprint":
        return (("by", "status"), ("by", "sprint"))
    return (("by", "status"),)


def read_bar(
    session: Session,
    raw: FilterRequest,
    *,
    base: str,
    include_projects: bool,
    extra: Sequence[tuple[str, str]] = (),
) -> ViewFilter:
    return view_filter.load(
        session,
        base=base,
        submitted=raw.submitted,
        types=raw.types,
        statuses=raw.statuses,
        priorities=raw.priorities,
        sprints=raw.sprints,
        labels=raw.labels,
        assignees=raw.assignees,
        reporters=raw.reporters,
        projects=raw.projects,
        label_add=raw.label_add,
        assignee_add=raw.assignee_add,
        reporter_add=raw.reporter_add,
        project_add=raw.project_add,
        include_projects=include_projects,
        extra=extra,
    )


def sprint_menu(
    session: Session,
    *,
    project_id: int | None,
    project_ids: tuple[int, ...],
) -> tuple[Sprint, ...]:
    if project_ids:
        found = [
            sprint
            for item_id in project_ids
            for sprint in sprint_service.list_sprints(session, item_id)
        ]
    elif project_id is not None:
        found = list(sprint_service.list_sprints(session, project_id))
    else:
        found = list(sprint_service.list_all_sprints(session))
    return board_service.board_sprint_choices(found)


def filter_context(
    bar: ViewFilter,
    *,
    action: str,
    show_project: bool,
    show_layout: bool,
    sprints: Sequence[Sprint],
    project_keys: dict[int, str],
    prefix: bool,
    separate: bool,
    preserve: Sequence[tuple[str, str]],
    error: str | None,
) -> dict[str, object]:
    return {
        "bar": bar,
        "filter_action": action,
        "show_project": show_project,
        "show_layout": show_layout,
        "issue_types": types_in_hierarchy_order(),
        "workflow_statuses": view_filter.status_choices(),
        "priority_levels": view_filter.priority_choices(),
        "sprints": sprints,
        "project_keys": project_keys,
        "prefix_sprints": prefix,
        "separate_by_sprint": separate,
        "preserve": preserve,
        "error": error or bar.error,
    }
