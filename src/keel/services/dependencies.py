from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from keel.db.models import Dependency, Issue
from keel.domain.enums import TERMINAL_STATUS, DependencyKind
from keel.domain.errors import (
    DependencyCycleError,
    DependencyDuplicateError,
    DependencySelfLinkError,
    NotFoundError,
)
from keel.domain.graph import would_create_cycle
from keel.services import issues as issue_service
from keel.services import projects as project_service


@dataclass(frozen=True)
class DependencyLink:
    id: int
    issue: Issue
    key: str
    project_key: str


@dataclass(frozen=True)
class IssueDependencies:
    blocks: tuple[DependencyLink, ...]
    blocked_by: tuple[DependencyLink, ...]
    relates_to: tuple[DependencyLink, ...]


def get_dependency(session: Session, dependency_id: int) -> Dependency:
    dependency = session.get(Dependency, dependency_id)
    if dependency is None:
        raise NotFoundError(f"No dependency with id {dependency_id}.")
    return dependency


def create_dependency(
    session: Session,
    source_id: int,
    target_id: int,
    kind: DependencyKind,
) -> Dependency:
    if source_id == target_id:
        raise DependencySelfLinkError(
            "An issue cannot depend on itself.",
            source_id=source_id,
            target_id=target_id,
        )
    source = issue_service.get_issue(session, source_id)
    target = issue_service.get_issue(session, target_id)
    existing = session.scalars(
        select(Dependency).where(
            Dependency.source_id == source.id,
            Dependency.target_id == target.id,
            Dependency.kind == kind,
        ),
    ).first()
    if existing is not None:
        raise DependencyDuplicateError(
            "That link already exists.",
            source_id=source.id,
            target_id=target.id,
            kind=kind.value,
        )
    if kind is DependencyKind.BLOCKS and would_create_cycle(
        _blocks_adjacency(session),
        source.id,
        target.id,
    ):
        source_key = _key(session, source)
        target_key = _key(session, target)
        raise DependencyCycleError(
            f"{target_key} already blocks {source_key} through an existing chain.",
            source_id=source.id,
            target_id=target.id,
        )
    dependency = Dependency(
        source_id=source.id,
        target_id=target.id,
        kind=kind,
    )
    session.add(dependency)
    session.flush()
    return dependency


def delete_dependency(session: Session, dependency_id: int) -> None:
    session.delete(get_dependency(session, dependency_id))
    session.flush()


def list_for_issue(session: Session, issue_id: int) -> IssueDependencies:
    issue = issue_service.get_issue(session, issue_id)
    rows = session.scalars(
        select(Dependency).where(
            (Dependency.source_id == issue.id) | (Dependency.target_id == issue.id),
        ),
    ).all()
    others = _issues_by_id(session, rows, issue.id)
    blocks: list[DependencyLink] = []
    blocked_by: list[DependencyLink] = []
    relates_to: list[DependencyLink] = []
    for row in rows:
        if row.kind is DependencyKind.BLOCKS:
            if row.source_id == issue.id:
                blocks.append(_link(session, row.id, others[row.target_id]))
            else:
                blocked_by.append(_link(session, row.id, others[row.source_id]))
        elif row.source_id == issue.id:
            relates_to.append(_link(session, row.id, others[row.target_id]))
        else:
            relates_to.append(_link(session, row.id, others[row.source_id]))
    return IssueDependencies(
        blocks=_sorted(blocks),
        blocked_by=_sorted(blocked_by),
        relates_to=_sorted(relates_to),
    )


def unresolved_blocker_counts(
    session: Session,
    issue_ids: Sequence[int],
) -> dict[int, int]:
    """Direct *blocks* links whose source is not Done, grouped by target."""
    if not issue_ids:
        return {}
    rows = session.execute(
        select(Dependency.target_id, func.count())
        .join(Issue, Issue.id == Dependency.source_id)
        .where(
            Dependency.kind == DependencyKind.BLOCKS,
            Dependency.target_id.in_(tuple(issue_ids)),
            Issue.status != TERMINAL_STATUS,
        )
        .group_by(Dependency.target_id),
    ).all()
    return {int(target_id): int(count) for target_id, count in rows}


def _blocks_adjacency(session: Session) -> dict[int, list[int]]:
    rows = session.execute(
        select(Dependency.source_id, Dependency.target_id).where(
            Dependency.kind == DependencyKind.BLOCKS,
        ),
    ).all()
    adjacency: dict[int, list[int]] = {}
    for source_id, target_id in rows:
        adjacency.setdefault(int(source_id), []).append(int(target_id))
    return adjacency


def _issues_by_id(
    session: Session,
    rows: Sequence[Dependency],
    issue_id: int,
) -> dict[int, Issue]:
    other_ids = {
        row.target_id if row.source_id == issue_id else row.source_id for row in rows
    }
    if not other_ids:
        return {}
    found = session.scalars(select(Issue).where(Issue.id.in_(other_ids))).all()
    return {issue.id: issue for issue in found}


def _link(session: Session, dependency_id: int, issue: Issue) -> DependencyLink:
    project = project_service.get_project(session, issue.project_id)
    return DependencyLink(
        id=dependency_id,
        issue=issue,
        key=issue_service.issue_key(issue, project),
        project_key=project.key,
    )


def _key(session: Session, issue: Issue) -> str:
    return issue_service.issue_key(
        issue,
        project_service.get_project(session, issue.project_id),
    )


def _sorted(links: Sequence[DependencyLink]) -> tuple[DependencyLink, ...]:
    return tuple(sorted(links, key=lambda link: (link.key, link.id)))
