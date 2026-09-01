# Keel

FastAPI web application with a small CLI for local development.

Requires **Python 3.12**.

## Setup

Onboarding scripts create `.venv`, install the package in editable mode with the `dev` extra from [`pyproject.toml`](pyproject.toml), verify Poe tasks, install git pre-commit hooks and their environments (`poe hooks`), run `poe isort-check` and `poe mypy`, and copy [`.env.example`](.env.example) to `.env` if it is missing. They require **Python 3.12+** (override with the `PYTHON` environment variable).

```powershell
.\scripts\onboard.ps1
.\.venv\Scripts\Activate.ps1
```

```bat
scripts\onboard.bat
.venv\Scripts\activate.bat
```

```bash
chmod +x scripts/onboard.sh
./scripts/onboard.sh
source .venv/bin/activate
```

Settings are read from the environment with the `KEEL_` prefix.

| Variable | Default | Description |
| --- | --- | --- |
| `KEEL_HOST` | `127.0.0.1` | Bind address |
| `KEEL_PORT` | `8000` | Bind port |
| `KEEL_RELOAD` | `false` | Uvicorn auto-reload |
| `KEEL_LOG_LEVEL` | `info` | Uvicorn log level |
| `KEEL_DATABASE_URL` | SQLite in the user data directory | Where Keel stores its data |
| `KEEL_DEFAULT_USER` | OS username | Who the app acts as before a picker choice |

## Database

Keel keeps a SQLite file outside the repository, in the OS user data directory (`%LOCALAPPDATA%\Keel\keel.db` on Windows). Create or update its schema before serving:

```powershell
keel db upgrade
```

`keel serve` refuses to start against a missing or out-of-date schema and tells you to run that command. After changing a model, generate a migration and review it before committing:

```powershell
keel db revision -m "describe the change"
```

## Run

```powershell
poe serve
```

Reload on file changes (`poe` forwards extra args to `keel serve`):

```powershell
poe serve --reload
```

Equivalent commands: `keel serve`, `python -m keel serve`, or Uvicorn directly:

```powershell
uvicorn keel.app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/` (HTML home page with the favicon), `http://127.0.0.1:8000/users` (manage who Keel knows about), and `http://127.0.0.1:8000/health`.

## Lint and test

```powershell
poe check
```

That runs [pre-commit](https://pre-commit.com/) on all files (including isort, mypy, and unit tests with 90% coverage), then pytest. Hooks also run on `git commit` after onboarding. Re-run `poe hooks` to reinstall git hooks and refresh hook environments.

Tests are grouped under `tests/`:

| Suite | Directory | Poe task |
| --- | --- | --- |
| Unit | `tests/unit/` | `poe test-unit` (must pass; **90%** coverage of `keel`) |
| Integration | `tests/integration/` | `poe test-integration` |
| System | `tests/system/` | `poe test-system` |
| All | `tests/` | `poe test` |

Add further suites the same way (directory + pytest marker + `poe test-<name>` task). Markers are applied from the directory name (`unit`, `integration`, `system`).

Individual tasks: `poe lint`, `poe format`, `poe format-check`, `poe isort`, `poe isort-check`, `poe mypy`, `poe pre-commit`, `poe test`. Run `poe` with no arguments to list them.

## Documentation

Keel is an issue tracker for one owner plus up to two collaborators. What it is and why is described in the architecture package; how it is built is described in the design package and the decision records.

| Area | Documents |
| --- | --- |
| Architecture | [Context](docs/architecture/context.md), [use cases](docs/architecture/use-cases.md), [domain model](docs/architecture/domain-model.md), [capabilities](docs/architecture/capabilities.md), [v1 scope](docs/architecture/v1-scope.md), [glossary](docs/architecture/glossary.md) |
| Design | [Data model](docs/design/data-model.md), [API reference](docs/design/api.md), [module layout](docs/design/module-layout.md), [UI design](docs/design/ui.md), [implementation plan](docs/design/implementation-plan.md) |
| Decisions | [ADRs](docs/adr/) — 001 and 002 cover the web chrome, 003 to 006 the domain, 007 to 014 the implementation |
| Other | [Brand colors](docs/brand-colors.md), [package version](docs/version.md) |

The [implementation plan](docs/design/implementation-plan.md) is the build order. Phase 0 (foundation, templates, users) is in place; projects and issues are next.

## License

This is not an open-source project. See [LICENSE](LICENSE) or the in-app page at `/license`.

