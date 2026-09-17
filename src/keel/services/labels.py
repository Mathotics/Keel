from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from keel.db.models import IssueLabel, Label
from keel.domain.labels import normalize_label_name, parse_label_names
from keel.services import history as history_service
from keel.services import issues as issue_service


def list_labels(session: Session) -> Sequence[Label]:
    return session.scalars(select(Label).order_by(Label.name)).all()


def names_for_issue(session: Session, issue_id: int) -> list[str]:
    return names_for_issues(session, (issue_id,)).get(issue_id, [])


def names_for_issues(
    session: Session,
    issue_ids: Sequence[int],
) -> dict[int, list[str]]:
    names: dict[int, list[str]] = {issue_id: [] for issue_id in issue_ids}
    if not issue_ids:
        return names
    rows = session.execute(
        select(IssueLabel.issue_id, Label.name)
        .join(Label, Label.id == IssueLabel.label_id)
        .where(IssueLabel.issue_id.in_(tuple(issue_ids)))
        .order_by(Label.name),
    ).all()
    for issue_id, name in rows:
        names.setdefault(issue_id, []).append(name)
    return names


def labels_for_issue(session: Session, issue_id: int) -> Sequence[Label]:
    return session.scalars(
        select(Label)
        .join(IssueLabel, IssueLabel.label_id == Label.id)
        .where(IssueLabel.issue_id == issue_id)
        .order_by(Label.name),
    ).all()


def set_issue_labels(
    session: Session,
    issue_id: int,
    values: Sequence[str] | str,
    *,
    actor_name: str | None = None,
    record_history: bool = True,
) -> list[str]:
    issue_service.get_issue(session, issue_id)
    wanted = tuple(sorted(parse_label_names(values)))
    current = tuple(names_for_issue(session, issue_id))
    if wanted == current:
        return list(current)
    if record_history:
        history_service.record(
            session,
            issue_id,
            field=history_service.FIELD_LABELS,
            from_value=history_service.labels_label(current),
            to_value=history_service.labels_label(wanted),
            actor_name=actor_name,
        )
    session.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id))
    session.flush()
    for name in wanted:
        label = _get_or_create(session, name)
        session.add(IssueLabel(issue_id=issue_id, label_id=label.id))
    session.flush()
    return list(wanted)


def add_issue_label(
    session: Session,
    issue_id: int,
    raw: str,
    *,
    actor_name: str | None = None,
) -> list[str]:
    current = names_for_issue(session, issue_id)
    name = normalize_label_name(raw)
    if name in current:
        return current
    return set_issue_labels(
        session,
        issue_id,
        (*current, name),
        actor_name=actor_name,
    )


def remove_issue_label(
    session: Session,
    issue_id: int,
    label_id: int,
    *,
    actor_name: str | None = None,
) -> list[str]:
    issue_service.get_issue(session, issue_id)
    current = labels_for_issue(session, issue_id)
    remaining = [label.name for label in current if label.id != label_id]
    if len(remaining) == len(current):
        return [label.name for label in current]
    return set_issue_labels(
        session,
        issue_id,
        remaining,
        actor_name=actor_name,
    )


def _get_or_create(session: Session, name: str) -> Label:
    found = session.scalars(select(Label).where(Label.name == name)).first()
    if found is not None:
        return found
    label = Label(name=name)
    session.add(label)
    session.flush()
    return label
