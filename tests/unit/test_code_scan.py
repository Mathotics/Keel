import json
from pathlib import Path

import pytest
from scripts.code_scan import (
    ScanError,
    browser_sources,
    eslint_problems,
    high_bandit,
    javascript_levels,
    nosec_problems,
    phone_sources,
    python_skips,
    python_sources,
)

_ROOT = Path(__file__).resolve().parents[2]
_IDS = {"B101", "B602"}
_RULES = {"detect-eval-with-expression", "detect-object-injection"}


def test_python_sources_are_the_server_and_not_tests() -> None:
    files = python_sources(_ROOT)
    assert files
    assert all(path.suffix == ".py" for path in files)
    assert all("src" in path.parts and "keel" in path.parts for path in files)
    assert all("tests" not in path.parts for path in files)


def test_browser_sources_are_the_shipping_scripts() -> None:
    files = browser_sources(_ROOT)
    assert files
    assert {path.name for path in files} >= {"nav.js", "board.js"}
    assert all(path.parent.name == "js" for path in files)


def test_phone_sources_skip_tests() -> None:
    files = phone_sources(_ROOT)
    assert any(path.name == "App.js" for path in files)
    assert all(not path.name.endswith(".test.js") for path in files)
    assert all("mobile" in path.parts for path in files)


def test_named_nosec_with_a_reason_is_a_waiver() -> None:
    text = "call()  # nosec B602 # the command list is constant\n"
    assert nosec_problems(text, _IDS) == []


def test_bare_nosec_is_not_a_waiver() -> None:
    problems = nosec_problems("call()  # nosec\n", _IDS)
    assert len(problems) == 1
    assert "name the finding" in problems[0][1]


def test_nosec_without_a_reason_is_not_a_waiver() -> None:
    problems = nosec_problems("call()  # nosec B602\n", _IDS)
    assert problems
    assert "reason" in problems[0][1]


def test_unknown_bandit_id_is_not_a_waiver() -> None:
    problems = nosec_problems("call()  # nosec B999 # not a real test\n", _IDS)
    assert problems
    assert "unknown" in problems[0][1]


def test_line_disable_with_a_reason_is_a_waiver() -> None:
    text = (
        "eval(name); "
        "// eslint-disable-next-line security/detect-eval-with-expression"
        " -- name is a fixed field\n"
    )
    known = {f"security/{rule}" for rule in _RULES}
    assert eslint_problems(text, known) == []


def test_file_disable_is_not_a_waiver() -> None:
    text = "/* eslint-disable security/detect-eval-with-expression -- no */\n"
    known = {f"security/{rule}" for rule in _RULES}
    problems = eslint_problems(text, known)
    assert problems
    assert "finding's line" in problems[0][1]


def test_disable_without_a_reason_is_not_a_waiver() -> None:
    text = "// eslint-disable-next-line security/detect-eval-with-expression\n"
    known = {f"security/{rule}" for rule in _RULES}
    problems = eslint_problems(text, known)
    assert problems
    assert "reason" in problems[0][1]


def test_high_bandit_findings_fail_and_lower_ones_do_not() -> None:
    issues: list[dict[str, object]] = [
        {"issue_severity": "LOW"},
        {"issue_severity": "MEDIUM"},
        {"issue_severity": "HIGH"},
        {"issue_severity": "CRITICAL"},
    ]
    failing = high_bandit(issues)
    assert [issue["issue_severity"] for issue in failing] == ["HIGH", "CRITICAL"]


def test_python_skip_requires_a_reason() -> None:
    with pytest.raises(ScanError, match="reason"):
        python_skips({"skips": [{"id": "B101", "reason": "  "}]})


def test_python_skip_with_a_reason_is_accepted() -> None:
    assert python_skips(
        {"skips": [{"id": "B101", "reason": "asserts stay without -O"}]}
    ) == ["B101"]


def test_javascript_off_rule_requires_a_reason() -> None:
    data = {
        "rules": {
            "detect-eval-with-expression": {"level": "off"},
            "detect-object-injection": {"level": "warn"},
        }
    }
    with pytest.raises(ScanError, match="reason"):
        javascript_levels(data, _RULES)


def test_javascript_config_must_name_every_scanner_rule() -> None:
    data = {"rules": {"detect-eval-with-expression": {"level": "error"}}}
    with pytest.raises(ScanError, match="does not match"):
        javascript_levels(data, _RULES)


def test_checked_in_configs_match_the_contract() -> None:
    python = json.loads((_ROOT / "scan" / "python.json").read_text(encoding="utf-8"))
    assert python_skips(python) == []
    plugin_rules = set(_RULES)
    for name in ("browser.json", "phone.json"):
        payload = json.loads((_ROOT / "scan" / name).read_text(encoding="utf-8"))
        rules = payload["rules"]
        sample = {rule: rules[rule] for rule in _RULES}
        levels = javascript_levels({"rules": sample}, plugin_rules)
        assert levels["security/detect-eval-with-expression"] == "error"
        assert levels["security/detect-object-injection"] == "warn"
