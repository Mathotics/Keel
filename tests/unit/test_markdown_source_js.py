import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_write_edits_match_the_behavior_catalog() -> None:
    node = shutil.which("node")
    assert node
    completed = subprocess.run(
        [
            node,
            "--test",
            "tests/js/markdown-source.test.js",
            "tests/js/markdown-preview.test.js",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
