"""Scan shipping code for security flaws.

A high or critical finding fails that app's check. Lower findings are printed
and do not fail it. A waiver is a suppression on the finding's line that the
scanner reads:

    # nosec B602 # why this call is safe
    // eslint-disable-next-line security/detect-eval-with-expression -- why

The id after nosec, or the security rule after eslint-disable-next-line, is
the finding. Text after the second # or after -- is the reason. A comment the
scanner does not read is not a waiver. A rule turned off for a whole app
belongs in that app's config under scan/, with a reason, and nowhere else.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scan"
_FAILING = {"HIGH", "CRITICAL"}
_JS_LEVELS = {"error", "warn", "off"}
_APPS = ("python", "browser", "phone")

_LIST_BANDIT_IDS = """
from bandit.core.extension_loader import MANAGER
ids = set(MANAGER.plugins_by_id) | set(MANAGER.blacklist_by_id)
print("\\n".join(sorted(ids)))
"""

_LIST_PLUGIN_RULES = (
    "const plugin = require('eslint-plugin-security');"
    "process.stdout.write(Object.keys(plugin.rules).sort().join('\\n'));"
)


class ScanError(Exception):
    """The scan did not finish, so the check fails."""


def python_sources(root: Path) -> list[Path]:
    server = root / "src" / "keel"
    return sorted(path for path in server.rglob("*.py") if path.is_file())


def browser_sources(root: Path) -> list[Path]:
    scripts = root / "assets" / "js"
    return sorted(path for path in scripts.glob("*.js") if path.is_file())


def phone_sources(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in ("App.js", "index.js"):
        path = root / "mobile" / name
        if path.is_file():
            found.append(path)
    for folder_name in ("plugins", "src"):
        folder = root / "mobile" / folder_name
        if not folder.is_dir():
            continue
        found.extend(
            path
            for path in folder.rglob("*.js")
            if path.is_file() and not path.name.endswith(".test.js")
        )
    return sorted(found)


def nosec_problems(text: str, known_ids: set[str]) -> list[tuple[int, str]]:
    """Return line numbers whose nosec comment is not a real waiver."""
    problems: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        problem = _nosec_line(line, known_ids)
        if problem is not None:
            problems.append((number, problem))
    return problems


def eslint_problems(text: str, known_rules: set[str]) -> list[tuple[int, str]]:
    """Return line numbers whose eslint-disable comment is not a real waiver."""
    problems: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        problem = _eslint_line(line, known_rules)
        if problem is not None:
            problems.append((number, problem))
    return problems


def python_skips(data: object) -> list[str]:
    """Return Bandit test ids turned off for the whole Python server."""
    if not isinstance(data, dict) or set(data) != {"skips"}:
        raise ScanError("scan/python.json must contain only skips")
    skips = cast(dict[str, object], data)["skips"]
    if not isinstance(skips, list):
        raise ScanError("scan/python.json skips must be a list")
    ids: list[str] = []
    for item in skips:
        if not isinstance(item, dict):
            raise ScanError("each Python skip needs an id and a reason")
        entry = cast(dict[str, object], item)
        if set(entry) != {"id", "reason"}:
            raise ScanError("each Python skip needs an id and a reason")
        test_id = entry["id"]
        reason = entry["reason"]
        if not isinstance(test_id, str) or not _is_bandit_id(test_id):
            raise ScanError("a Python skip id must look like B101")
        if not isinstance(reason, str) or not reason.strip():
            raise ScanError(f"{test_id} is turned off and needs a reason")
        ids.append(test_id)
    return ids


def javascript_levels(data: object, plugin_rules: set[str]) -> dict[str, str]:
    """Return ESLint levels for one app.

    error fails the check. warn is shown and does not. off needs a reason.
    """
    if not isinstance(data, dict) or set(data) != {"rules"}:
        raise ScanError("a JavaScript config must contain only rules")
    raw_rules = cast(dict[str, object], data)["rules"]
    if not isinstance(raw_rules, dict):
        raise ScanError("JavaScript rules must be an object")
    rules = cast(dict[str, object], raw_rules)
    missing = plugin_rules - set(rules)
    extra = set(rules) - plugin_rules
    if missing or extra:
        detail = ", ".join(sorted(missing or extra))
        raise ScanError(f"JavaScript config does not match the scanner rules: {detail}")
    levels: dict[str, str] = {}
    for rule, spec in rules.items():
        if not isinstance(spec, dict):
            raise ScanError(f"{rule} needs a level")
        entry = cast(dict[str, object], spec)
        level = entry.get("level")
        if not isinstance(level, str) or level not in _JS_LEVELS:
            raise ScanError(f"{rule} level must be error, warn, or off")
        if level == "off":
            reason = entry.get("reason")
            if set(entry) != {"level", "reason"}:
                raise ScanError(f"{rule} is turned off and needs a reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ScanError(f"{rule} is turned off and needs a reason")
        elif set(entry) != {"level"}:
            raise ScanError(f"{rule} does not take a reason unless it is off")
        levels[f"security/{rule}"] = level
    return levels


def high_bandit(issues: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        issue
        for issue in issues
        if str(issue.get("issue_severity", "")).upper() in _FAILING
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    if len(args) != 2 or args[1] not in _APPS:
        print(
            "usage: python scripts/code_scan.py python|browser|phone",
            file=sys.stderr,
        )
        return 2
    app = args[1]
    try:
        if app == "python":
            return _scan_python()
        return _scan_javascript(app)
    except ScanError as exc:
        print(f"{app}: {exc}", file=sys.stderr)
        return 1


def _nosec_line(line: str, known_ids: set[str]) -> str | None:
    marker = re.search(r"#\s*nosec\b", line, re.IGNORECASE)
    if marker is None:
        return None
    comment = line[marker.start() :]
    pieces = [part.strip() for part in comment.split("#")]
    # "# nosec B101 # reason" -> ["", "nosec B101", "reason"]
    if len(pieces) < 3 or not pieces[1].lower().startswith("nosec"):
        return (
            "a waiver must name the finding and a reason: "
            "# nosec B602 # why this call is safe"
        )
    body = pieces[1][len("nosec") :].strip()
    reason = pieces[2]
    if not reason:
        return "a waiver needs a reason after the second #"
    if not body:
        return "a waiver must name the Bandit finding, such as B602"
    ids = [part.strip() for part in body.split(",")]
    if not ids or any(not _is_bandit_id(test_id) for test_id in ids):
        return "a waiver must name the Bandit finding, such as B602"
    unknown = [test_id for test_id in ids if test_id not in known_ids]
    if unknown:
        return f"unknown Bandit finding: {', '.join(unknown)}"
    return None


def _eslint_line(line: str, known_rules: set[str]) -> str | None:
    marker = line.find("eslint-disable")
    if marker < 0:
        return None
    directive = line[marker:].strip()
    prefix = "eslint-disable-next-line"
    same_line = "eslint-disable-line"
    if directive.startswith(prefix):
        body = directive[len(prefix) :]
    elif directive.startswith(same_line):
        body = directive[len(same_line) :]
    else:
        return (
            "a waiver must be on the finding's line and name that finding: "
            "// eslint-disable-next-line security/detect-eval-with-expression"
            " -- why"
        )
    if "--" not in body:
        return "a waiver needs a reason after --"
    rules_text, reason = body.split("--", 1)
    if not reason.strip():
        return "a waiver needs a reason after --"
    rules = [part.strip().rstrip(",").strip() for part in rules_text.split(",")]
    rules = [rule for rule in rules if rule]
    if not rules or any(not rule.startswith("security/") for rule in rules):
        return "a waiver must name the security finding"
    unknown = [rule for rule in rules if rule not in known_rules]
    if unknown:
        return f"unknown security finding: {', '.join(unknown)}"
    return None


def _is_bandit_id(test_id: str) -> bool:
    return len(test_id) > 1 and test_id[0] == "B" and test_id[1:].isdigit()


def _scan_python() -> int:
    files = python_sources(ROOT)
    if not files:
        raise ScanError("no Python server files to scan")
    skips = python_skips(_load_json(SCAN / "python.json"))
    known_ids = _bandit_ids()
    unknown_skips = [test_id for test_id in skips if test_id not in known_ids]
    if unknown_skips:
        raise ScanError(f"unknown Bandit finding: {', '.join(unknown_skips)}")
    problems = _waiver_problems(files, lambda text: nosec_problems(text, known_ids))
    if problems:
        _print_problems(problems)
        return 1
    command = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        "src/keel",
        "-f",
        "json",
        "-q",
    ]
    if skips:
        command.extend(["--skip", ",".join(skips)])
    completed = _run(command)
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or "Bandit did not finish"
        raise ScanError(detail)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ScanError("Bandit did not finish") from exc
    if not isinstance(payload, dict):
        raise ScanError("Bandit did not finish")
    raw_results = cast(dict[str, object], payload).get("results", [])
    if not isinstance(raw_results, list):
        raise ScanError("Bandit did not finish")
    issues = [
        cast(dict[str, object], item) for item in raw_results if isinstance(item, dict)
    ]
    issues.sort(key=_bandit_sort_key)
    for issue in issues:
        severity = str(issue.get("issue_severity", "")).upper()
        location = _rel(Path(str(issue.get("filename", ""))))
        line = issue.get("line_number", "?")
        test_id = issue.get("test_id", "")
        text = issue.get("issue_text", "")
        print(f"{severity}  {location}:{line}  {test_id}  {text}")
    failing = high_bandit(issues)
    print(f"python: {len(issues)} findings, {len(failing)} high or critical")
    return 1 if failing else 0


def _scan_javascript(app: str) -> int:
    files = browser_sources(ROOT) if app == "browser" else phone_sources(ROOT)
    if not files:
        raise ScanError(f"no {app} files to scan")
    plugin_rules = _plugin_rules()
    levels = javascript_levels(_load_json(SCAN / f"{app}.json"), plugin_rules)
    known_rules = set(levels)
    problems = _waiver_problems(files, lambda text: eslint_problems(text, known_rules))
    if problems:
        _print_problems(problems)
        return 1
    eslint = SCAN / "node_modules" / "eslint" / "bin" / "eslint.js"
    if not eslint.is_file():
        raise ScanError("ESLint is not installed; run npm ci --prefix scan")
    config = SCAN / "_eslint.config.mjs"
    config.write_text(
        _eslint_config(levels, jsx=app == "phone"),
        encoding="utf-8",
    )
    try:
        completed = _run(
            [
                "node",
                str(eslint),
                "--config",
                str(config),
                "-f",
                "json",
                *[str(path) for path in files],
            ]
        )
    finally:
        config.unlink(missing_ok=True)
    if completed.returncode not in {0, 1}:
        detail = (completed.stderr or completed.stdout).strip()
        raise ScanError(detail or "ESLint did not finish")
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ScanError("ESLint did not finish") from exc
    if not isinstance(payload, list):
        raise ScanError("ESLint did not finish")
    messages = _eslint_messages(payload)
    if any(item["fatal"] for item in messages):
        _print_eslint(messages)
        raise ScanError("ESLint could not read a file")
    messages.sort(key=lambda item: (item["path"], item["line"], item["rule"]))
    _print_eslint(messages)
    failing = [item for item in messages if item["severity"] == "error"]
    print(f"{app}: {len(messages)} findings, {len(failing)} high or critical")
    return 1 if failing else 0


def _eslint_messages(payload: list[object]) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for file_result in payload:
        if not isinstance(file_result, dict):
            raise ScanError("ESLint did not finish")
        result = cast(dict[str, object], file_result)
        path = _rel(Path(str(result.get("filePath", ""))))
        raw_messages = result.get("messages", [])
        if not isinstance(raw_messages, list):
            raise ScanError("ESLint did not finish")
        for raw in raw_messages:
            if not isinstance(raw, dict):
                raise ScanError("ESLint did not finish")
            message = cast(dict[str, object], raw)
            severity_code = message.get("severity", 0)
            severity = "error" if severity_code == 2 else "warn"
            messages.append(
                {
                    "path": path,
                    "line": message.get("line", "?"),
                    "rule": message.get("ruleId") or "",
                    "text": message.get("message", ""),
                    "severity": severity,
                    "fatal": bool(message.get("fatal", False)),
                }
            )
    return messages


def _print_eslint(messages: list[dict[str, object]]) -> None:
    for message in messages:
        label = "HIGH" if message["severity"] == "error" else "LOW"
        print(
            f"{label}  {message['path']}:{message['line']}  "
            f"{message['rule']}  {message['text']}"
        )


def _eslint_config(levels: dict[str, str], *, jsx: bool) -> str:
    rules = ",\n".join(
        f"      {json.dumps(rule)}: {json.dumps(level)}"
        for rule, level in sorted(levels.items())
    )
    return (
        'import security from "eslint-plugin-security";\n\n'
        "export default [\n"
        "  {\n"
        "    plugins: { security },\n"
        "    languageOptions: {\n"
        "      ecmaVersion: 2024,\n"
        f"      sourceType: {json.dumps('module' if jsx else 'script')},\n"
        "      parserOptions: { ecmaFeatures: { jsx: "
        f"{'true' if jsx else 'false'} }} }},\n"
        "    },\n"
        '    linterOptions: { reportUnusedDisableDirectives: "error" },\n'
        "    rules: {\n"
        f"{rules}\n"
        "    },\n"
        "  },\n"
        "];\n"
    )


def _waiver_problems(
    files: list[Path],
    check: Callable[[str], list[tuple[int, str]]],
) -> list[str]:
    problems: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ScanError(f"could not read {_rel(path)}: {exc}") from exc
        except UnicodeError as exc:
            raise ScanError(f"could not read {_rel(path)}") from exc
        for number, problem in check(text):
            problems.append(f"{_rel(path)}:{number}  {problem}")
    return problems


def _print_problems(problems: list[str]) -> None:
    for problem in problems:
        print(problem)


def _bandit_ids() -> set[str]:
    completed = _run([sys.executable, "-c", _LIST_BANDIT_IDS])
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Bandit is not installed"
        raise ScanError(detail)
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _plugin_rules() -> set[str]:
    completed = _run(["node", "-e", _LIST_PLUGIN_RULES], cwd=SCAN)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or (
            "ESLint is not installed; run npm ci --prefix scan"
        )
        raise ScanError(detail)
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _load_json(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScanError(f"could not read {_rel(path)}") from exc


def _run(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT if cwd is None else cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScanError("the scan did not finish") from exc
    except OSError as exc:
        raise ScanError(f"the scan could not start: {exc}") from exc


def _bandit_sort_key(issue: dict[str, object]) -> tuple[str, int]:
    line = issue.get("line_number", 0)
    return (
        str(issue.get("filename", "")),
        line if isinstance(line, int) else 0,
    )


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _venv_python() -> Path | None:
    """Return the project virtualenv interpreter, when this checkout has one."""
    for relative in (
        Path(".venv") / "Scripts" / "python.exe",
        Path(".venv") / "bin" / "python",
    ):
        candidate = ROOT / relative
        if candidate.is_file():
            return candidate
    return None


def _same_python(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


if __name__ == "__main__":
    # Git runs hooks with whatever `python` is on PATH. Bandit lives in the
    # virtualenv, so a commit from outside that env continues there.
    venv_python = _venv_python()
    if venv_python is not None and not _same_python(venv_python, Path(sys.executable)):
        raise SystemExit(subprocess.call([str(venv_python), *sys.argv]))
    raise SystemExit(main())
