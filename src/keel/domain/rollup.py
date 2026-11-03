from collections.abc import Sequence
from dataclasses import dataclass

from keel.domain.enums import COMPLETED_STATUS, IssueStatus
from keel.domain.money import estimate_at_completion, performance_index


@dataclass(frozen=True)
class EffortNode:
    id: int
    estimate_minutes: int | None
    remaining_minutes: int | None
    status: IssueStatus
    planned_value_cents: int | None = None
    earned_value_cents: int | None = None
    actual_cost_cents: int | None = None


@dataclass(frozen=True)
class Rollup:
    """Subtree totals. Unset values contribute nothing; None means none were set."""

    estimate_minutes: int | None
    remaining_minutes: int | None
    descendants: int
    descendants_done: int
    descendants_cancelled: int
    planned_value_cents: int | None
    earned_value_cents: int | None
    actual_cost_cents: int | None
    budget_at_completion_cents: int | None
    estimate_at_completion_cents: int | None
    schedule_performance_index: float | None
    cost_performance_index: float | None

    def progress_sentence(self) -> str:
        text = f"{self.descendants_done} of {self.descendants} done"
        if self.descendants_cancelled:
            return f"{text}, {self.descendants_cancelled} cancelled"
        return text


def compute_rollup(root_id: int, nodes: Sequence[EffortNode]) -> Rollup:
    own = next(node for node in nodes if node.id == root_id)
    descendants = tuple(node for node in nodes if node.id != root_id)
    open_remaining = (
        node.remaining_minutes
        for node in descendants
        if node.status is not IssueStatus.CANCELLED
    )
    planned = _sum_present(
        own.planned_value_cents,
        *(node.planned_value_cents for node in descendants),
    )
    earned = _sum_present(
        own.earned_value_cents,
        *(node.earned_value_cents for node in descendants),
    )
    actual = _sum_present(
        own.actual_cost_cents,
        *(node.actual_cost_cents for node in descendants),
    )
    return Rollup(
        estimate_minutes=_sum_present(
            own.estimate_minutes,
            *(node.estimate_minutes for node in descendants),
        ),
        remaining_minutes=_sum_present(own.remaining_minutes, *open_remaining),
        descendants=len(descendants),
        descendants_done=sum(
            1 for node in descendants if node.status is COMPLETED_STATUS
        ),
        descendants_cancelled=sum(
            1 for node in descendants if node.status is IssueStatus.CANCELLED
        ),
        planned_value_cents=planned,
        earned_value_cents=earned,
        actual_cost_cents=actual,
        budget_at_completion_cents=planned,
        estimate_at_completion_cents=estimate_at_completion(planned, earned, actual),
        schedule_performance_index=performance_index(earned, planned),
        cost_performance_index=performance_index(earned, actual),
    )


def _sum_present(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)
