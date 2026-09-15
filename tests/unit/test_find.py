from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueStatus, IssueType
from keel.services import comments as comment_service
from keel.services import find as find_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.find import PER_KIND, FindJump, FindResults


def project(session: Session, key: str = "KEEL", name: str = "Keel") -> Project:
    return project_service.create_project(session, key, name)


def story(
    session: Session,
    owner: Project,
    title: str = "Something",
    **kwargs: object,
) -> int:
    issue = issue_service.create_issue(
        session,
        owner.id,
        type=IssueType.STORY,
        title=title,
        **kwargs,  # type: ignore[arg-type]
    )
    return issue.id


def test_empty_query_does_not_jump(session: Session) -> None:
    outcome = find_service.find(session, "  ")
    assert isinstance(outcome, FindResults)
    assert outcome.empty
    owner = project(session)
    story(session, owner, title="Rework onboarding")
    outcome = find_service.find(session, "keel-1")
    assert isinstance(outcome, FindJump)
    assert outcome.url == "/issues/KEEL-1"


def test_a_project_key_jumps_when_it_is_not_an_issue_key(session: Session) -> None:
    project(session)
    outcome = find_service.find(session, "keel")
    assert isinstance(outcome, FindJump)
    assert outcome.url == "/projects/KEEL"


def test_a_unique_user_name_jumps_to_users(session: Session) -> None:
    user_service.create_user(session, "Ada")
    outcome = find_service.find(session, "ada")
    assert isinstance(outcome, FindJump)
    assert outcome.url == "/users"


def test_a_unique_sprint_name_jumps_in_scope(session: Session) -> None:
    owner = project(session)
    other = project(session, "SITE", "Site")
    sprint = sprint_service.create_sprint(session, owner.id, "Sprint 1")
    sprint_service.create_sprint(session, other.id, "Sprint 1")
    outcome = find_service.find(session, "Sprint 1", project_id=owner.id)
    assert isinstance(outcome, FindJump)
    assert outcome.url == f"/projects/KEEL/sprints/{sprint.id}"


def test_a_shared_sprint_name_lists_instead_of_jumping(session: Session) -> None:
    owner = project(session)
    other = project(session, "SITE", "Site")
    sprint_service.create_sprint(session, owner.id, "Sprint 1")
    sprint_service.create_sprint(session, other.id, "Sprint 1")
    outcome = find_service.find(session, "Sprint 1")
    assert isinstance(outcome, FindResults)
    assert len(outcome.sprints) == 2


def test_title_matches_list_issues(session: Session) -> None:
    owner = project(session)
    story(session, owner, title="Rework the onboarding script")
    outcome = find_service.find(session, "onboarding")
    assert isinstance(outcome, FindResults)
    assert [hit.key for hit in outcome.issues] == ["KEEL-1"]
    assert outcome.issues[0].snippet is None


def test_description_and_comment_matches_open_the_issue(session: Session) -> None:
    owner = project(session)
    described = story(session, owner, title="Quiet", description="mentions a widget")
    commented = story(session, owner, title="Also quiet")
    comment_service.create_comment(session, commented, "the widget is stuck")
    outcome = find_service.find(session, "widget")
    assert isinstance(outcome, FindResults)
    assert {hit.key for hit in outcome.issues} == {
        issue_service.issue_key(
            issue_service.get_issue(session, described),
            owner,
        ),
        issue_service.issue_key(
            issue_service.get_issue(session, commented),
            owner,
        ),
    }
    assert all(hit.snippet is not None for hit in outcome.issues)


def test_done_issues_and_completed_sprints_are_included(session: Session) -> None:
    owner = project(session)
    story(session, owner, title="Shipped widget", status=IssueStatus.DONE)
    sprint = sprint_service.create_sprint(session, owner.id, "Done sprint")
    sprint_service.start_sprint(session, sprint.id)
    sprint_service.complete_sprint(session, sprint.id)
    issues = find_service.find(session, "widget")
    sprints = find_service.find(session, "Done sprint")
    assert isinstance(issues, FindResults)
    assert [hit.key for hit in issues.issues] == ["KEEL-1"]
    assert isinstance(sprints, FindJump)
    assert sprints.url.endswith(f"/sprints/{sprint.id}")


def test_scope_hides_other_projects_issues(session: Session) -> None:
    owner = project(session)
    other = project(session, "SITE", "Site")
    story(session, owner, title="Shared word")
    story(session, other, title="Shared word")
    outcome = find_service.find(session, "Shared", project_id=owner.id)
    assert isinstance(outcome, FindResults)
    assert [hit.key for hit in outcome.issues] == ["KEEL-1"]
    assert not outcome.projects
    other_project = find_service.find(session, "SITE", project_id=owner.id)
    assert isinstance(other_project, FindJump)
    assert other_project.url == "/projects/SITE"


def test_no_match_is_an_empty_list(session: Session) -> None:
    project(session)
    outcome = find_service.find(session, "xyzzy")
    assert isinstance(outcome, FindResults)
    assert outcome.empty


def test_a_missing_issue_key_does_not_jump(session: Session) -> None:
    project(session)
    outcome = find_service.find(session, "KEEL-99")
    assert isinstance(outcome, FindResults)
    assert outcome.empty


def test_the_list_caps_each_kind(session: Session) -> None:
    owner = project(session)
    for index in range(PER_KIND + 1):
        story(session, owner, title=f"Needle {index}")
    outcome = find_service.find(session, "Needle")
    assert isinstance(outcome, FindResults)
    assert len(outcome.issues) == PER_KIND
    assert outcome.issues_more is True


def test_project_description_and_sprint_goal_match(session: Session) -> None:
    owner = project(session, "KEEL", "Keel")
    project_service.update_project(session, owner.id, description="holds a gadget")
    sprint_service.create_sprint(session, owner.id, "Alpha", goal="ship the gadget")
    outcome = find_service.find(session, "gadget")
    assert isinstance(outcome, FindResults)
    assert [hit.key for hit in outcome.projects] == ["KEEL"]
    assert outcome.projects[0].snippet is not None
    assert [hit.name for hit in outcome.sprints] == ["Alpha"]
    assert outcome.sprints[0].snippet is not None


def test_a_long_match_is_trimmed_with_ellipsis(session: Session) -> None:
    owner = project(session)
    padding = "word " * 20
    story(session, owner, title="Quiet", description=f"{padding}needle{padding}")
    outcome = find_service.find(session, "needle")
    assert isinstance(outcome, FindResults)
    snippet = outcome.issues[0].snippet
    assert snippet is not None
    assert snippet.startswith("…")
    assert snippet.endswith("…")


def test_like_wildcards_are_literal(session: Session) -> None:
    owner = project(session)
    story(session, owner, title="Ordinary")
    outcome = find_service.find(session, "%")
    assert isinstance(outcome, FindResults)
    assert outcome.empty


def test_find_does_not_search_issue_history(session: Session) -> None:
    owner = project(session)
    issue_id = story(session, owner, title="Quiet")
    issue_service.update_issue(session, issue_id, remaining_minutes=90)
    outcome = find_service.find(session, "1h 30m")
    assert isinstance(outcome, FindResults)
    assert outcome.empty
