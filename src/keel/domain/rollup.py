from collections.abc import Sequence
from dataclasses import dataclass

from keel.domain.enums import TERMINAL_STATUS, IssueStatus


@dataclass(frozen=True)
class EffortNode:
    id: int
    estimate_minutes: int | None
    remaining_minutes: int | None
    status: IssueStatus


@dataclass(frozen=True)
class Rollup:
    """Subtree totals. Unset values contribute nothing; None means none were set."""

    estimate_minutes: int | None
    remaining_minutes: int | None
    descendants: int
    descendants_done: int


def compute_rollup(root_id: int, nodes: Sequence[EffortNode]) -> Rollup:
    own = next(node for node in nodes if node.id == root_id)
    descendants = tuple(node for node in nodes if node.id != root_id)
    return Rollup(
        estimate_minutes=_sum_present(
            own.estimate_minutes,
            *(node.estimate_minutes for node in descendants),
        ),
        remaining_minutes=_sum_present(
            own.remaining_minutes,
            *(node.remaining_minutes for node in descendants),
        ),
        descendants=len(descendants),
        descendants_done=sum(
            1 for node in descendants if node.status is TERMINAL_STATUS
        ),
    )


def _sum_present(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)
