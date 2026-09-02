from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from keel.domain.enums import IssueType
from keel.domain.errors import (
    InvalidParentError,
    InvalidParentTypeError,
    ParentCycleError,
)

# The only legal parent for each type. None means the type never has a parent.
PARENT_TYPE: dict[IssueType, IssueType | None] = {
    IssueType.EPIC: None,
    IssueType.STORY: IssueType.EPIC,
    IssueType.SUBTASK: IssueType.STORY,
}


@dataclass(frozen=True)
class IssueRef:
    """The little an issue needs to expose for the hierarchy rules to judge it."""

    id: int | None
    type: IssueType
    project_id: int


def check_parent(
    child: IssueRef,
    parent: IssueRef | None,
    ancestor_ids: Sequence[int] = (),
) -> None:
    """Validate a proposed parent. No parent is always legal.

    `ancestor_ids` walks upward from the proposed parent, so the service reads
    the chain from the database and the rule itself stays free of queries.
    """
    if parent is None:
        return

    if parent.project_id != child.project_id:
        raise InvalidParentError(
            "A parent must belong to the same project as its child.",
            child_id=child.id,
            parent_id=parent.id,
        )

    expected = PARENT_TYPE[child.type]
    if expected is None:
        raise InvalidParentTypeError(
            f"An {child.type.value} never has a parent.",
            child_type=child.type.value,
            parent_type=parent.type.value,
        )
    if parent.type is not expected:
        raise InvalidParentTypeError(
            f"A {child.type.value} may only sit under {an(expected.value)}.",
            child_type=child.type.value,
            parent_type=parent.type.value,
            expected_parent_type=expected.value,
        )

    if child.id is not None and child.id in {parent.id, *ancestor_ids}:
        raise ParentCycleError(
            "That parent would make the issue its own ancestor.",
            child_id=child.id,
            parent_id=parent.id,
        )


def child_type_of(parent_type: IssueType) -> IssueType | None:
    """The type that may sit directly under this parent, or none if none may."""
    for child, parent in PARENT_TYPE.items():
        if parent is parent_type:
            return child
    return None


def check_children(new_type: IssueType, child_types: Iterable[IssueType]) -> None:
    """Guard a type change against the children the issue already has."""
    for child_type in child_types:
        if PARENT_TYPE[child_type] is not new_type:
            raise InvalidParentTypeError(
                f"Existing {child_type.value} children cannot sit under "
                f"{an(new_type.value)}.",
                new_type=new_type.value,
                child_type=child_type.value,
            )


def an(word: str) -> str:
    return f"an {word}" if word[0] in "aeiou" else f"a {word}"
