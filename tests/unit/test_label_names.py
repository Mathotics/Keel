import pytest

from keel.domain.errors import InvalidIssueError
from keel.domain.labels import normalize_label_name, parse_label_names


def test_names_are_trimmed_lowercased_and_hyphenated() -> None:
    assert normalize_label_name("  Bug Fix  ") == "bug-fix"


def test_an_empty_name_is_refused() -> None:
    with pytest.raises(InvalidIssueError, match="needs a name"):
        normalize_label_name("   ")


def test_illegal_characters_are_refused() -> None:
    with pytest.raises(InvalidIssueError, match="letters, digits"):
        normalize_label_name("bug!")


def test_a_too_long_name_is_refused() -> None:
    with pytest.raises(InvalidIssueError, match="at most"):
        normalize_label_name("a" * 41)


def test_comma_separated_names_are_unique_and_sorted_by_parse_order() -> None:
    assert parse_label_names("Urgent, bug, urgent") == ("urgent", "bug")


def test_a_list_of_names_is_normalized() -> None:
    assert parse_label_names([" Frontend ", "backend"]) == ("frontend", "backend")


def test_blank_tokens_are_dropped() -> None:
    assert parse_label_names("urgent,,  ,bug") == ("urgent", "bug")
