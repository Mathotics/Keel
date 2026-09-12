import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import DependencyKind, IssueStatus, IssueType
from keel.domain.errors import (
    DependencyCycleError,
    DependencyDuplicateError,
    DependencySelfLinkError,
    NotFoundError,
)
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import projects as project_service


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def story(session: Session, project: Project, title: str, **kwargs: object) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=title,
        **kwargs,  # type: ignore[arg-type]
    ).id


def test_a_blocks_link_is_stored(session: Session, project: Project) -> None:
    source = story(session, project, "First")
    target = story(session, project, "Second")

    link = dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )

    assert link.source_id == source
    assert link.target_id == target
    assert link.kind is DependencyKind.BLOCKS


def test_a_self_link_is_refused(session: Session, project: Project) -> None:
    issue_id = story(session, project, "Alone")

    with pytest.raises(DependencySelfLinkError) as caught:
        dependency_service.create_dependency(
            session,
            issue_id,
            issue_id,
            DependencyKind.RELATES_TO,
        )
    assert caught.value.code == "dependency.self_link"


def test_a_duplicate_link_is_refused(session: Session, project: Project) -> None:
    source = story(session, project, "First")
    target = story(session, project, "Second")
    dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )

    with pytest.raises(DependencyDuplicateError) as caught:
        dependency_service.create_dependency(
            session,
            source,
            target,
            DependencyKind.BLOCKS,
        )
    assert caught.value.code == "dependency.duplicate"


def test_the_reverse_blocks_link_closes_a_cycle(
    session: Session,
    project: Project,
) -> None:
    first = story(session, project, "First")
    second = story(session, project, "Second")
    dependency_service.create_dependency(
        session,
        first,
        second,
        DependencyKind.BLOCKS,
    )

    with pytest.raises(DependencyCycleError) as caught:
        dependency_service.create_dependency(
            session,
            second,
            first,
            DependencyKind.BLOCKS,
        )
    assert caught.value.code == "dependency.cycle"
    assert "already blocks" in caught.value.message


def test_a_chain_cannot_loop_back(session: Session, project: Project) -> None:
    first = story(session, project, "First")
    second = story(session, project, "Second")
    third = story(session, project, "Third")
    dependency_service.create_dependency(
        session,
        first,
        second,
        DependencyKind.BLOCKS,
    )
    dependency_service.create_dependency(
        session,
        second,
        third,
        DependencyKind.BLOCKS,
    )

    with pytest.raises(DependencyCycleError):
        dependency_service.create_dependency(
            session,
            third,
            first,
            DependencyKind.BLOCKS,
        )


def test_relates_to_does_not_participate_in_cycles(
    session: Session,
    project: Project,
) -> None:
    first = story(session, project, "First")
    second = story(session, project, "Second")
    dependency_service.create_dependency(
        session,
        first,
        second,
        DependencyKind.RELATES_TO,
    )
    dependency_service.create_dependency(
        session,
        second,
        first,
        DependencyKind.BLOCKS,
    )


def test_links_may_cross_projects(session: Session, project: Project) -> None:
    site = project_service.create_project(session, "SITE", "Site")
    source = story(session, project, "Local")
    target = story(session, site, "Foreign")

    dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )
    groups = dependency_service.list_for_issue(session, source)
    assert [link.key for link in groups.blocks] == ["SITE-1"]
    assert groups.blocks[0].project_key == "SITE"

    incoming = dependency_service.list_for_issue(session, target)
    assert [link.key for link in incoming.blocked_by] == ["KEEL-1"]


def test_a_cycle_that_leaves_and_reenters_a_project_is_refused(
    session: Session,
    project: Project,
) -> None:
    site = project_service.create_project(session, "SITE", "Site")
    local = story(session, project, "Local")
    foreign = story(session, site, "Foreign")
    dependency_service.create_dependency(
        session,
        local,
        foreign,
        DependencyKind.BLOCKS,
    )

    with pytest.raises(DependencyCycleError):
        dependency_service.create_dependency(
            session,
            foreign,
            local,
            DependencyKind.BLOCKS,
        )


def test_relates_to_is_listed_from_either_end(
    session: Session,
    project: Project,
) -> None:
    first = story(session, project, "First")
    second = story(session, project, "Second")
    dependency_service.create_dependency(
        session,
        first,
        second,
        DependencyKind.RELATES_TO,
    )

    first_links = dependency_service.list_for_issue(session, first).relates_to
    second_links = dependency_service.list_for_issue(session, second).relates_to
    assert [link.key for link in first_links] == ["KEEL-2"]
    assert [link.key for link in second_links] == ["KEEL-1"]


def test_deleting_a_link_removes_it(session: Session, project: Project) -> None:
    source = story(session, project, "First")
    target = story(session, project, "Second")
    link = dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )
    dependency_service.delete_dependency(session, link.id)

    groups = dependency_service.list_for_issue(session, source)
    assert groups.blocks == ()
    with pytest.raises(NotFoundError):
        dependency_service.get_dependency(session, link.id)


def test_deleting_an_issue_cascades_its_links(
    session: Session,
    project: Project,
) -> None:
    source = story(session, project, "First")
    target = story(session, project, "Second")
    link = dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )
    link_id = link.id
    issue_service.delete_issue(session, source)
    session.expire_all()

    groups = dependency_service.list_for_issue(session, target)
    assert groups.blocked_by == ()
    with pytest.raises(NotFoundError):
        dependency_service.get_dependency(session, link_id)


def test_deleting_a_project_removes_cross_project_links(
    session: Session,
    project: Project,
) -> None:
    site = project_service.create_project(session, "SITE", "Site")
    source = story(session, project, "Local")
    target = story(session, site, "Foreign")
    dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.BLOCKS,
    )
    project_service.delete_project(session, project.id)
    session.expire_all()

    groups = dependency_service.list_for_issue(session, target)
    assert groups.blocked_by == ()


def test_unresolved_blocker_counts_ignore_done_sources(
    session: Session,
    project: Project,
) -> None:
    blocker = story(session, project, "Blocker")
    other = story(session, project, "Also")
    waiting = story(session, project, "Waiting")
    dependency_service.create_dependency(
        session,
        blocker,
        waiting,
        DependencyKind.BLOCKS,
    )
    dependency_service.create_dependency(
        session,
        other,
        waiting,
        DependencyKind.BLOCKS,
    )
    issue_service.update_issue(session, blocker, status=IssueStatus.DONE)

    counts = dependency_service.unresolved_blocker_counts(session, (waiting,))
    assert counts == {waiting: 1}


def test_unresolved_blocker_counts_keep_cancelled_sources(
    session: Session,
    project: Project,
) -> None:
    blocker = story(session, project, "Blocker")
    waiting = story(session, project, "Waiting")
    dependency_service.create_dependency(
        session,
        blocker,
        waiting,
        DependencyKind.BLOCKS,
    )
    issue_service.update_issue(session, blocker, status=IssueStatus.CANCELLED)

    counts = dependency_service.unresolved_blocker_counts(session, (waiting,))
    assert counts == {waiting: 1}


def test_relates_to_does_not_count_as_a_blocker(
    session: Session,
    project: Project,
) -> None:
    source = story(session, project, "Related")
    target = story(session, project, "Waiting")
    dependency_service.create_dependency(
        session,
        source,
        target,
        DependencyKind.RELATES_TO,
    )

    assert dependency_service.unresolved_blocker_counts(session, (target,)) == {}
