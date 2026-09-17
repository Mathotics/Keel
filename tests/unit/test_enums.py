from keel.domain.enums import (
    INITIAL_PRIORITY,
    IssuePriority,
    label,
    priorities_in_rank_order,
)


def test_priority_rank_runs_from_blocker_to_trivial() -> None:
    assert [item.value for item in priorities_in_rank_order()] == [
        "p1",
        "p2",
        "p3",
        "p4",
        "p5",
    ]
    assert INITIAL_PRIORITY is IssuePriority.P4
    assert label(IssuePriority.P1) == "P1 — Blocker"
    assert label(IssuePriority.P3) == "P3 — Major"
    assert label(IssuePriority.P4) == "P4 — Minor"
    assert label(IssuePriority.P5) == "P5 — Trivial"
