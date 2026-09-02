from keel.domain.enums import IssueStatus
from keel.domain.rollup import EffortNode, compute_rollup


def test_a_lone_issue_has_no_descendants() -> None:
    rollup = compute_rollup(
        1,
        [EffortNode(1, 120, 60, IssueStatus.TODO)],
    )
    assert rollup.estimate_minutes == 120
    assert rollup.remaining_minutes == 60
    assert rollup.descendants == 0
    assert rollup.descendants_done == 0


def test_unset_effort_contributes_nothing_and_stays_absent() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, None, None, IssueStatus.TODO),
            EffortNode(2, None, None, IssueStatus.DONE),
        ],
    )
    assert rollup.estimate_minutes is None
    assert rollup.remaining_minutes is None
    assert rollup.descendants == 1
    assert rollup.descendants_done == 1


def test_own_and_descendant_estimates_add_without_replacing_own() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, 120, 120, IssueStatus.TODO),
            EffortNode(2, 60, 30, IssueStatus.DONE),
            EffortNode(3, None, 15, IssueStatus.TODO),
        ],
    )
    assert rollup.estimate_minutes == 180
    assert rollup.remaining_minutes == 165
    assert rollup.descendants == 2
    assert rollup.descendants_done == 1


def test_progress_counts_only_descendants() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, 0, 0, IssueStatus.DONE),
            EffortNode(2, 30, 0, IssueStatus.DONE),
            EffortNode(3, 30, 30, IssueStatus.TODO),
        ],
    )
    assert rollup.descendants == 2
    assert rollup.descendants_done == 1
