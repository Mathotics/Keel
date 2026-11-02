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
    assert rollup.descendants_cancelled == 0
    assert rollup.progress_sentence() == "0 of 0 done"


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
    assert rollup.descendants_cancelled == 0
    assert rollup.progress_sentence() == "1 of 2 done"


def test_cancelled_descendants_are_counted_separately_and_omit_remaining() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, 120, 120, IssueStatus.TODO),
            EffortNode(2, 60, 30, IssueStatus.DONE),
            EffortNode(3, 45, 45, IssueStatus.CANCELLED),
            EffortNode(4, None, 15, IssueStatus.TODO),
        ],
    )
    assert rollup.estimate_minutes == 225
    assert rollup.remaining_minutes == 165
    assert rollup.descendants == 3
    assert rollup.descendants_done == 1
    assert rollup.descendants_cancelled == 1
    assert rollup.progress_sentence() == "1 of 3 done, 1 cancelled"


def test_cost_sums_include_cancelled_work_and_skip_unset_values() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, None, None, IssueStatus.TODO, 10000, 4000, 5000),
            EffortNode(2, None, None, IssueStatus.DONE, 5000, 5000, None),
            EffortNode(3, None, None, IssueStatus.CANCELLED, None, 0, 2500),
            EffortNode(4, None, None, IssueStatus.TODO, None, None, None),
        ],
    )
    assert rollup.planned_value_cents == 15000
    assert rollup.earned_value_cents == 9000
    assert rollup.actual_cost_cents == 7500
    assert rollup.budget_at_completion_cents == 15000
    assert rollup.estimate_at_completion_cents == 13500
    assert rollup.schedule_performance_index == 0.6
    assert rollup.cost_performance_index == 1.2


def test_indexes_use_the_sums_rather_than_an_average_of_children() -> None:
    rollup = compute_rollup(
        1,
        [
            EffortNode(1, None, None, IssueStatus.TODO, 10000, 5000, 5000),
            EffortNode(2, None, None, IssueStatus.TODO, 10000, 10000, 20000),
        ],
    )
    assert rollup.schedule_performance_index == 0.75
    assert rollup.cost_performance_index == 0.6


def test_indexes_are_absent_until_the_divisor_is_set() -> None:
    rollup = compute_rollup(
        1,
        [EffortNode(1, None, None, IssueStatus.TODO, None, 100, 0)],
    )
    assert rollup.budget_at_completion_cents is None
    assert rollup.estimate_at_completion_cents is None
    assert rollup.schedule_performance_index is None
    assert rollup.cost_performance_index is None
