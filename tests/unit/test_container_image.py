from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_image_installs_the_tree_keel_paths_reads() -> None:
    dockerfile = _text("Dockerfile")
    assert "FROM python:3.12-slim-bookworm" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY assets ./assets" in dockerfile
    assert "COPY pyproject.toml README.md LICENSE ./" in dockerfile
    assert "pip install --no-cache-dir -e ." in dockerfile
    assert "USER keel" in dockerfile
    assert "VOLUME /data" in dockerfile
    assert "sqlite+pysqlite:////data/keel.db" in dockerfile
    assert "KEEL_HOST=0.0.0.0" in dockerfile
    assert "/health" in dockerfile


def test_entrypoint_upgrades_before_serve_and_runs_other_commands() -> None:
    script = _text("deploy/docker-entrypoint.sh")
    upgrade_at = script.index("keel db upgrade")
    exec_at = script.index('exec "$@"')
    assert upgrade_at < exec_at
    assert "set -- keel serve" in script
    assert '[ "$1" = "keel" ]' in script
    assert '[ "${2:-}" = "serve" ]' in script


def test_compose_publishes_the_data_volume() -> None:
    compose = _text("compose.yaml")
    assert "sqlite+pysqlite:////data/keel.db" in compose
    assert "keel-data:/data" in compose
    assert '"8000:8000"' in compose
    assert "KEEL_HOST: 0.0.0.0" in compose


def test_image_build_omits_secrets_and_keeps_shell_scripts_lf() -> None:
    ignored = _text(".dockerignore")
    assert "\n.env\n" in f"\n{ignored}"
    attributes = _text(".gitattributes")
    assert "deploy/docker-entrypoint.sh text eol=lf" in attributes
    assert "s/\\r$//" in _text("Dockerfile")
