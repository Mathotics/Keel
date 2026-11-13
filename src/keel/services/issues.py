import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from keel.db.models import Issue, IssueLabel, Label, Project, Sprint
from keel.domain.enums import (
    CLOSED_STATUSES,
    INITIAL_PRIORITY,
    INITIAL_STATUS,
    IssuePriority,
    IssueStatus,
    IssueType,
    SprintState,
    statuses_in_workflow_order,
)
from keel.domain.errors import (
    DuplicateSubmitError,
    InvalidIssueError,
    IssueHasChildrenError,
    NotFoundError,
    SprintProjectMismatchError,
)
from keel.domain.hierarchy import IssueRef, check_children, check_parent
from keel.domain.labels import parse_label_names
from keel.domain.rollup import EffortNode, Rollup, compute_rollup
from keel.domain.schedule import check_start_due_window
from keel.services import projects as project_service

MAX_TITLE_LENGTH = 300
MAX_LOCATION_LENGTH = 300
UNSET = object()
_CLIENT_KEY = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_DUPLICATE_SUBMIT = "That create was already used. Reload the page and try again."


@dataclass(frozen=True)
class IssueFilters:
    type: IssueType | None = None
    types: tuple[IssueType, ...] = ()
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    assignee_id: int | None = None
    unassigned: bool = False
    parent_id: int | None = None
    sprint_id: int | None = None
    unscheduled: bool = False
    label: str | None = None
    unlabeled: bool = False
    hide_closed_in_completed_sprints: bool = False
    require_type: bool = False
    statuses: tuple[IssueStatus, ...] = ()
    priorities: tuple[IssuePriority, ...] = ()
    assignee_any: bool = False
    assignee_ids: tuple[int, ...] = ()
    sprint_any: bool = False
    sprint_ids: tuple[int, ...] = ()
    label_any: bool = False
    labels: tuple[str, ...] = ()
    reporter_any: bool = False
    reporter_ids: tuple[int, ...] = ()
    reporter_none: bool = False
    project_ids: tuple[int, ...] = ()
    start_from: date | None = None
    start_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None


def issue_key(issue: Issue, project: Project) -> str:
    return f"{project.key}-{issue.number}"


def get_issue(session: Session, issue_id: int) -> Issue:
    issue = session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError(f"No issue with id {issue_id}.")
    return issue


def get_issue_by_key(session: Session, key: str) -> Issue:
    """Resolves the readable `KEEL-12` form used in web URLs."""
    project_key, _, number = key.rpartition("-")
    if not project_key or not number.isdigit():
        raise NotFoundError(f"{key} is not an issue key.")
    project = project_service.get_project_by_key(session, project_key)
    issue = session.scalars(
        select(Issue).where(
            Issue.project_id == project.id,
            Issue.number == int(number),
        ),
    ).first()
    if issue is None:
        raise NotFoundError(f"No issue {key}.")
    return issue


def list_issues(
    session: Session,
    project_id: int | None = None,
    filters: IssueFilters | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> Sequence[Issue]:
    query = select(Issue)
    if project_id is not None:
        query = query.where(Issue.project_id == project_id).order_by(Issue.number)
    else:
        query = query.join(Project, Issue.project_id == Project.id).order_by(
            Project.key,
            Issue.number,
        )
    query = _apply_filters(query, filters or IssueFilters())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return session.scalars(query).all()


def list_issues_globally(session: Session) -> Sequence[Issue]:
    """Every issue, for pickers that may cross projects."""
    return session.scalars(
        select(Issue)
        .join(Project, Issue.project_id == Project.id)
        .order_by(Project.key, Issue.number),
    ).all()


def count_by_status(session: Session, project_id: int) -> dict[IssueStatus, int]:
    """Every status appears, including the ones with nothing in them."""
    counts = dict.fromkeys(statuses_in_workflow_order(), 0)
    rows = session.execute(
        select(Issue.status, func.count())
        .where(Issue.project_id == project_id)
        .group_by(Issue.status),
    ).all()
    for status, total in rows:
        counts[status] = total
    return counts


def list_children(session: Session, issue_id: int) -> Sequence[Issue]:
    return session.scalars(
        select(Issue).where(Issue.parent_id == issue_id).order_by(Issue.number),
    ).all()


def new_client_key() -> str:
    """A create token the form or the phone can send back unchanged."""
    return secrets.token_urlsafe(16)


def create_issue(
    session: Session,
    project_id: int,
    type: IssueType,
    title: str,
    description: str = "",
    definition_of_done: str = "",
    location: str = "",
    status: IssueStatus = INITIAL_STATUS,
    priority: IssuePriority = INITIAL_PRIORITY,
    parent_id: int | None = None,
    reporter_id: int | None = None,
    assignee_id: int | None = None,
    start_at: datetime | None = None,
    due_at: datetime | None = None,
    sprint_id: int | None = None,
    estimate_minutes: int | None = None,
    remaining_minutes: int | None = None,
    planned_value_cents: int | None = None,
    earned_value_cents: int | None = None,
    actual_cost_cents: int | None = None,
    series_id: int | None = None,
    series_item_id: int | None = None,
    occurrence_on: date | None = None,
    labels: Sequence[str] | str = (),
    client_key: str | None = None,
) -> Issue:
    project = project_service.get_project(session, project_id)
    key = _clean_client_key(client_key)
    if key is not None:
        already = _resubmitted_issue(session, key, project.id, reporter_id)
        if already is not None:
            return already
    _check_minutes(estimate_minutes)
    _check_minutes(remaining_minutes)
    _check_cents(planned_value_cents)
    _check_cents(earned_value_cents)
    _check_cents(actual_cost_cents)
    wanted_labels = parse_label_names(labels) if labels else ()
    check_start_due_window(start_at, due_at)
    if remaining_minutes is None:
        remaining_minutes = estimate_minutes
    issue = Issue(
        project_id=project.id,
        number=project_service.next_issue_number(session, project),
        type=type,
        title=_clean_title(title),
        description=description.strip(),
        definition_of_done=definition_of_done.strip(),
        location=_clean_location(location),
        status=status,
        priority=priority,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
        start_at=start_at,
        due_at=due_at,
        estimate_minutes=estimate_minutes,
        remaining_minutes=remaining_minutes,
        planned_value_cents=planned_value_cents,
        earned_value_cents=earned_value_cents,
        actual_cost_cents=actual_cost_cents,
        series_id=series_id,
        series_item_id=series_item_id,
        occurrence_on=occurrence_on,
        client_key=key,
    )
    _assign_parent(session, issue, parent_id)
    _assign_sprint(session, issue, sprint_id)
    fresh = issue
    issue = _flush_new_issue(session, issue, key, project.id, reporter_id)
    if issue is not fresh:
        return issue
    if wanted_labels:
        from keel.services import labels as label_service

        label_service.set_issue_labels(
            session,
            issue.id,
            wanted_labels,
            record_history=False,
            notify=False,
        )
    if issue.assignee_id is not None:
        from keel.services import notifications as notification_service
        from keel.services.identity import acting_user_id

        notification_service.record_assignment(
            session,
            issue,
            actor_id=acting_user_id(),
        )
    return issue


def update_issue(
    session: Session,
    issue_id: int,
    *,
    type: IssueType | None = None,
    title: str | None = None,
    description: str | None = None,
    definition_of_done: str | None = None,
    location: str | None = None,
    status: IssueStatus | None = None,
    priority: IssuePriority | None = None,
    parent_id: int | None | object = UNSET,
    assignee_id: int | None | object = UNSET,
    start_at: datetime | None | object = UNSET,
    due_at: datetime | None | object = UNSET,
    sprint_id: int | None | object = UNSET,
    estimate_minutes: int | None | object = UNSET,
    remaining_minutes: int | None | object = UNSET,
    planned_value_cents: int | None | object = UNSET,
    earned_value_cents: int | None | object = UNSET,
    actual_cost_cents: int | None | object = UNSET,
    labels: Sequence[str] | str | object = UNSET,
    actor_name: str | None = None,
) -> Issue:
    """Nullable fields accept None as "clear it", so they use UNSET."""
    from keel.services import history as history_service

    issue = get_issue(session, issue_id)
    who = actor_name if actor_name is not None else history_service.current_actor_name()
    changed_lines: list[str] = []
    assigned_to: int | None = None

    def _note(field: str, before: str, after: str) -> None:
        history_service.record(
            session,
            issue.id,
            field=field,
            from_value=before,
            to_value=after,
            actor_name=who,
        )
        changed_lines.append(f"{field}: {before} → {after}")

    if type is not None and type is not issue.type:
        check_children(type, [child.type for child in list_children(session, issue.id)])
        _note(
            history_service.FIELD_TYPE,
            history_service.type_label(issue.type),
            history_service.type_label(type),
        )
        issue.type = type
        _assign_parent(session, issue, issue.parent_id)

    if title is not None:
        cleaned_title = _clean_title(title)
        if cleaned_title != issue.title:
            _note(history_service.FIELD_TITLE, issue.title, cleaned_title)
            issue.title = cleaned_title
    if description is not None:
        cleaned_description = description.strip()
        if cleaned_description != issue.description:
            _note(
                history_service.FIELD_DESCRIPTION,
                history_service.text_label(issue.description),
                history_service.text_label(cleaned_description),
            )
            issue.description = cleaned_description
    if definition_of_done is not None:
        cleaned_done = definition_of_done.strip()
        if cleaned_done != issue.definition_of_done:
            _note(
                history_service.FIELD_DEFINITION_OF_DONE,
                history_service.text_label(issue.definition_of_done),
                history_service.text_label(cleaned_done),
            )
            issue.definition_of_done = cleaned_done
    if location is not None:
        cleaned_location = _clean_location(location)
        if cleaned_location != issue.location:
            _note(
                history_service.FIELD_LOCATION,
                history_service.text_label(issue.location),
                history_service.text_label(cleaned_location),
            )
            issue.location = cleaned_location
    if status is not None and status is not issue.status:
        _note(
            history_service.FIELD_STATUS,
            history_service.status_label(issue.status),
            history_service.status_label(status),
        )
        issue.status = status
    if priority is not None and priority is not issue.priority:
        _note(
            history_service.FIELD_PRIORITY,
            history_service.priority_label(issue.priority),
            history_service.priority_label(priority),
        )
        issue.priority = priority
    if parent_id is not UNSET and parent_id != issue.parent_id:
        old_parent = history_service.parent_label(session, issue.parent_id)
        new_parent = history_service.parent_label(session, parent_id)  # type: ignore[arg-type]
        _assign_parent(session, issue, parent_id)  # type: ignore[arg-type]
        _note(history_service.FIELD_PARENT, old_parent, new_parent)
    if assignee_id is not UNSET and assignee_id != issue.assignee_id:
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_ASSIGNEE,
            from_value=history_service.assignee_label(session, issue.assignee_id),
            to_value=history_service.assignee_label(session, assignee_id),  # type: ignore[arg-type]
            actor_name=who,
        )
        issue.assignee_id = assignee_id  # type: ignore[assignment]
        if isinstance(assignee_id, int):
            assigned_to = assignee_id
    if start_at is not UNSET:
        issue.start_at = start_at  # type: ignore[assignment]
    if due_at is not UNSET and due_at != issue.due_at:
        _note(
            history_service.FIELD_DUE,
            history_service.due_label(issue.due_at),
            history_service.due_label(due_at),  # type: ignore[arg-type]
        )
        issue.due_at = due_at  # type: ignore[assignment]
    check_start_due_window(issue.start_at, issue.due_at)
    if sprint_id is not UNSET and sprint_id != issue.sprint_id:
        old_sprint = history_service.sprint_label(session, issue.sprint_id)
        new_sprint = history_service.sprint_label(session, sprint_id)  # type: ignore[arg-type]
        _assign_sprint(session, issue, sprint_id)  # type: ignore[arg-type]
        _note(history_service.FIELD_SPRINT, old_sprint, new_sprint)
    if estimate_minutes is not UNSET:
        _check_minutes(estimate_minutes)  # type: ignore[arg-type]
        if estimate_minutes != issue.estimate_minutes:
            _note(
                history_service.FIELD_ESTIMATE,
                history_service.effort_label(issue.estimate_minutes),
                history_service.effort_label(estimate_minutes),  # type: ignore[arg-type]
            )
            issue.estimate_minutes = estimate_minutes  # type: ignore[assignment]
    if remaining_minutes is not UNSET:
        _check_minutes(remaining_minutes)  # type: ignore[arg-type]
        if remaining_minutes != issue.remaining_minutes:
            _note(
                history_service.FIELD_REMAINING,
                history_service.effort_label(issue.remaining_minutes),
                history_service.effort_label(remaining_minutes),  # type: ignore[arg-type]
            )
            issue.remaining_minutes = remaining_minutes  # type: ignore[assignment]
    cost_currency = project_service.get_project(session, issue.project_id).currency
    if planned_value_cents is not UNSET:
        _check_cents(planned_value_cents)  # type: ignore[arg-type]
        if planned_value_cents != issue.planned_value_cents:
            _note(
                history_service.FIELD_PLANNED_VALUE,
                history_service.cost_label(issue.planned_value_cents, cost_currency),
                history_service.cost_label(
                    planned_value_cents,  # type: ignore[arg-type]
                    cost_currency,
                ),
            )
            issue.planned_value_cents = planned_value_cents  # type: ignore[assignment]
    if earned_value_cents is not UNSET:
        _check_cents(earned_value_cents)  # type: ignore[arg-type]
        if earned_value_cents != issue.earned_value_cents:
            _note(
                history_service.FIELD_EARNED_VALUE,
                history_service.cost_label(issue.earned_value_cents, cost_currency),
                history_service.cost_label(
                    earned_value_cents,  # type: ignore[arg-type]
                    cost_currency,
                ),
            )
            issue.earned_value_cents = earned_value_cents  # type: ignore[assignment]
    if actual_cost_cents is not UNSET:
        _check_cents(actual_cost_cents)  # type: ignore[arg-type]
        if actual_cost_cents != issue.actual_cost_cents:
            _note(
                history_service.FIELD_ACTUAL_COST,
                history_service.cost_label(issue.actual_cost_cents, cost_currency),
                history_service.cost_label(
                    actual_cost_cents,  # type: ignore[arg-type]
                    cost_currency,
                ),
            )
            issue.actual_cost_cents = actual_cost_cents  # type: ignore[assignment]
    if labels is not UNSET:
        from keel.services import labels as label_service

        before_labels = label_service.names_for_issue(session, issue.id)
        label_service.set_issue_labels(
            session,
            issue.id,
            labels,  # type: ignore[arg-type]
            actor_name=who,
            notify=False,
        )
        after_labels = label_service.names_for_issue(session, issue.id)
        if before_labels != after_labels:
            changed_lines.append(
                f"{history_service.FIELD_LABELS}: "
                f"{history_service.labels_label(before_labels)} → "
                f"{history_service.labels_label(after_labels)}",
            )

    session.flush()
    if status is not None:
        from keel.services import series as series_service

        series_service.on_occurrence_closed(session, issue)
    _publish_issue_edit(session, issue, who, changed_lines, assigned_to)
    return issue


def notify_issue_deleted(session: Session, issue: Issue) -> None:
    from keel.services import notifications as notification_service

    notification_service.record_delete(session, issue)


def _publish_issue_edit(
    session: Session,
    issue: Issue,
    actor_name: str,
    lines: list[str],
    assigned_to: int | None,
) -> None:
    from keel.services import notifications as notification_service
    from keel.services.history import SYSTEM_ACTOR
    from keel.services.identity import acting_user_id

    if actor_name == SYSTEM_ACTOR:
        return
    actor_id = acting_user_id()
    if lines:
        notification_service.record_update(
            session,
            issue,
            lines,
            actor_name=actor_name,
            actor_id=actor_id,
        )
    if assigned_to is not None:
        notification_service.record_assignment(session, issue, actor_id=actor_id)


def delete_issue(session: Session, issue_id: int) -> None:
    issue = get_issue(session, issue_id)
    if (
        issue.series_id is not None
        and issue.occurrence_on is not None
        and issue.series_item_id is None
    ):
        from keel.services import series as series_service

        series_service.delete_occurrence(session, issue)
        return
    children = list_children(session, issue.id)
    if children:
        raise IssueHasChildrenError(
            "Move or delete this issue's children first.",
            issue_id=issue.id,
            children=len(children),
        )
    series_id = issue.series_id
    occurrence_on = issue.occurrence_on
    is_root = issue.series_item_id is None
    notify_issue_deleted(session, issue)
    session.delete(issue)
    session.flush()
    if series_id is not None and occurrence_on is not None and is_root:
        from keel.services import series as series_service

        series_service.after_issue_deleted(session, series_id, occurrence_on)


def issue_rollup(session: Session, issue_id: int) -> Rollup:
    """Subtree totals for one issue, loaded with a recursive parent walk."""
    issue = get_issue(session, issue_id)
    nodes = [
        EffortNode(
            id=item.id,
            estimate_minutes=item.estimate_minutes,
            remaining_minutes=item.remaining_minutes,
            status=item.status,
            planned_value_cents=item.planned_value_cents,
            earned_value_cents=item.earned_value_cents,
            actual_cost_cents=item.actual_cost_cents,
        )
        for item in _load_subtree(session, issue.id)
    ]
    return compute_rollup(issue.id, nodes)


def ancestor_ids(session: Session, issue_id: int) -> list[int]:
    """Walks upward from an issue, stopping if the data already holds a loop."""
    seen: list[int] = []
    current = session.get(Issue, issue_id)
    while current is not None and current.parent_id is not None:
        if current.parent_id in seen:
            break
        seen.append(current.parent_id)
        current = session.get(Issue, current.parent_id)
    return seen


def _assign_parent(session: Session, issue: Issue, parent_id: int | None) -> None:
    parent = None if parent_id is None else get_issue(session, parent_id)
    check_parent(
        IssueRef(id=issue.id, type=issue.type, project_id=issue.project_id),
        None
        if parent is None
        else IssueRef(id=parent.id, type=parent.type, project_id=parent.project_id),
        () if parent is None else ancestor_ids(session, parent.id),
    )
    issue.parent_id = parent_id


def _assign_sprint(session: Session, issue: Issue, sprint_id: int | None) -> None:
    if sprint_id is None:
        issue.sprint_id = None
        return
    from keel.services.sprints import get_sprint

    sprint = get_sprint(session, sprint_id)
    if sprint.project_id != issue.project_id:
        raise SprintProjectMismatchError(
            "An issue can only be scheduled in a sprint of the same project.",
            issue_id=issue.id,
            sprint_id=sprint.id,
        )
    issue.sprint_id = sprint_id


def restrict(query: Select[Any], filters: IssueFilters) -> Select[Any]:
    """Apply the same issue narrowing a list uses, on any issue select."""
    return _apply_filters(query, filters)


def _has_label(name: str) -> Any:
    return exists(
        select(IssueLabel.issue_id)
        .join(Label, Label.id == IssueLabel.label_id)
        .where(IssueLabel.issue_id == Issue.id, Label.name == name),
    )


def _has_no_label() -> Any:
    return ~exists(
        select(IssueLabel.issue_id).where(IssueLabel.issue_id == Issue.id),
    )


def _apply_filters(query: Select[Any], filters: IssueFilters) -> Select[Any]:
    if filters.require_type:
        if filters.types:
            query = query.where(Issue.type.in_(tuple(filters.types)))
        else:
            query = query.where(false())
    elif filters.types:
        chosen = set(filters.types)
        if chosen != set(IssueType):
            query = query.where(Issue.type.in_(filters.types))
    elif filters.type is not None:
        query = query.where(Issue.type == filters.type)
    if filters.statuses:
        query = query.where(Issue.status.in_(tuple(filters.statuses)))
    elif filters.status is not None:
        query = query.where(Issue.status == filters.status)
    if filters.priorities:
        query = query.where(Issue.priority.in_(tuple(filters.priorities)))
    elif filters.priority is not None:
        query = query.where(Issue.priority == filters.priority)
    if filters.assignee_any:
        people: list[Any] = []
        if filters.unassigned:
            people.append(Issue.assignee_id.is_(None))
        if filters.assignee_ids:
            people.append(Issue.assignee_id.in_(tuple(filters.assignee_ids)))
        if people:
            query = query.where(or_(*people))
    elif filters.unassigned:
        query = query.where(Issue.assignee_id.is_(None))
    elif filters.assignee_id is not None:
        query = query.where(Issue.assignee_id == filters.assignee_id)
    if filters.reporter_any:
        reporters: list[Any] = []
        if filters.reporter_none:
            reporters.append(Issue.reporter_id.is_(None))
        if filters.reporter_ids:
            reporters.append(Issue.reporter_id.in_(tuple(filters.reporter_ids)))
        if reporters:
            query = query.where(or_(*reporters))
    if filters.parent_id is not None:
        query = query.where(Issue.parent_id == filters.parent_id)
    if filters.sprint_any:
        windows: list[Any] = []
        if filters.unscheduled:
            windows.append(Issue.sprint_id.is_(None))
        if filters.sprint_ids:
            windows.append(Issue.sprint_id.in_(tuple(filters.sprint_ids)))
        if windows:
            query = query.where(or_(*windows))
    elif filters.unscheduled:
        query = query.where(Issue.sprint_id.is_(None))
    elif filters.sprint_id is not None:
        query = query.where(Issue.sprint_id == filters.sprint_id)
    if filters.label_any:
        marks: list[Any] = []
        if filters.unlabeled:
            marks.append(_has_no_label())
        marks.extend(_has_label(name) for name in filters.labels)
        if marks:
            query = query.where(or_(*marks))
    elif filters.unlabeled:
        query = query.where(_has_no_label())
    elif filters.label is not None:
        query = query.where(_has_label(filters.label))
    if filters.project_ids:
        query = query.where(Issue.project_id.in_(tuple(filters.project_ids)))
    start_window = _on_calendar_days(
        Issue.start_at,
        filters.start_from,
        filters.start_to,
    )
    if start_window is not None:
        query = query.where(start_window)
    due_window = _on_calendar_days(Issue.due_at, filters.due_from, filters.due_to)
    if due_window is not None:
        query = query.where(due_window)
    if filters.hide_closed_in_completed_sprints:
        query = query.where(
            ~exists(
                select(Sprint.id).where(
                    Sprint.id == Issue.sprint_id,
                    Sprint.state == SprintState.COMPLETED,
                    Issue.status.in_(CLOSED_STATUSES),
                ),
            ),
        )
    return query


def _on_calendar_days(column: Any, start: date | None, end: date | None) -> Any:
    """Inclusive calendar days. Either bound also drops rows with no timestamp."""
    if start is None and end is None:
        return None
    clauses: list[Any] = [column.is_not(None)]
    if start is not None:
        clauses.append(column >= datetime.combine(start, time.min))
    if end is not None:
        clauses.append(column < datetime.combine(end + timedelta(days=1), time.min))
    return and_(*clauses)


def _load_subtree(session: Session, root_id: int) -> Sequence[Issue]:
    tree = (
        select(Issue.id)
        .where(Issue.id == root_id)
        .cte(
            name="issue_tree",
            recursive=True,
        )
    )
    tree = tree.union_all(select(Issue.id).where(Issue.parent_id == tree.c.id))
    return session.scalars(
        select(Issue).where(Issue.id.in_(select(tree.c.id))).order_by(Issue.id),
    ).all()


def parse_due_at(raw: str) -> datetime | None:
    """Read a datetime-local or ISO string. Blank means no due date."""
    return parse_datetime(raw, "Due date")


def parse_start_at(raw: str) -> datetime | None:
    """Read a datetime-local or ISO string. Blank means no start date."""
    return parse_datetime(raw, "Start date")


def parse_datetime(raw: str, field: str) -> datetime | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise InvalidIssueError(f"{field} could not be read.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _clean_client_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if _CLIENT_KEY.fullmatch(cleaned) is None:
        raise InvalidIssueError(
            "A create key must be 16 to 64 letters, digits, hyphens, or underscores.",
        )
    return cleaned


def _resubmitted_issue(
    session: Session,
    client_key: str,
    project_id: int,
    reporter_id: int | None,
) -> Issue | None:
    found = session.scalars(
        select(Issue).where(Issue.client_key == client_key),
    ).first()
    if found is None:
        return None
    if found.project_id != project_id or found.reporter_id != reporter_id:
        raise DuplicateSubmitError(_DUPLICATE_SUBMIT)
    return found


def _flush_new_issue(
    session: Session,
    issue: Issue,
    client_key: str | None,
    project_id: int,
    reporter_id: int | None,
) -> Issue:
    """Inserts the issue. A key collision returns the issue that won the race."""
    # The counter flush has to land before the savepoint. begin_nested() flushes
    # pending objects first, and a unique failure there rolls back the request.
    session.flush()
    if client_key is None:
        session.add(issue)
        session.flush()
        return issue
    try:
        with session.begin_nested():
            session.add(issue)
            session.flush()
    except IntegrityError:
        # The failed insert stays pending. Drop it before the lookup, or the
        # request commit flushes it again and files a second issue.
        if issue in session:
            session.expunge(issue)
        found = _resubmitted_issue(session, client_key, project_id, reporter_id)
        if found is None:
            raise
        return found
    return issue


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise InvalidIssueError("An issue needs a title.")
    return cleaned[:MAX_TITLE_LENGTH]


def _clean_location(location: str) -> str:
    return location.strip()[:MAX_LOCATION_LENGTH]


def _check_minutes(value: int | None) -> None:
    if value is not None and value < 0:
        raise InvalidIssueError("Effort cannot be negative.")


def _check_cents(value: int | None) -> None:
    if value is not None and value < 0:
        raise InvalidIssueError("Cost cannot be negative.")
