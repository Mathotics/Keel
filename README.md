# Keel

Keel is a personal issue tracker for **one owner plus up to two collaborators**. It is a lightweight, Jira-flavored tool you host yourself: start it with `keel serve` and work in a browser.

Projects hold epics, stories, and subtasks on a shared workflow. Each project has a backlog, a Kanban board, time-boxed sprints, repeating schedules, and directed issue links. There is no login, no organization hierarchy, and no third-party integrations — v1 is built for a trusted local or small-group setup.

The same FastAPI application serves the pages, a JSON API, and a small CLI. Requires **Python 3.12**.

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

Copy the live database to a timestamped file next to it (or to a path you name). Restore a chosen file over the live database; `--yes` is required when that would overwrite an existing file. Both commands may run while `keel serve` is up; restart serve after a restore so it is not holding the old file.

```powershell
keel db backup
keel db backup path/to/copy.db
keel db restore path/to/copy.db
keel db restore --yes path/to/copy.db
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

Then open `http://127.0.0.1:8000/` (the acting user's inbox). Also `http://127.0.0.1:8000/projects` (the project directory, with a create form), `http://127.0.0.1:8000/create` (file an issue), `http://127.0.0.1:8000/users` (manage who Keel knows about) and `http://127.0.0.1:8000/health`. A project page lives at `/projects/KEEL`, its board at `/projects/KEEL/board`, its backlog at `/projects/KEEL/backlog`, its sprints at `/projects/KEEL/sprints`, its schedules at `/projects/KEEL/schedules`, and an issue at `/issues/KEEL-1`. The find field in the menu jumps to an exact key or lists matches at `/search`. The issue page is where comments, estimates, remaining time, priority, and dependencies are edited.

## Production

Production is the owner's Raspberry Pi. After bootstrap, every push to `main` that passes CI updates that machine with no further steps ([ADR 026](docs/adr/ADR-026.md)).

The app runs as a user systemd unit (`keel serve` from `/mnt/library/Keel/.venv`). It binds all interfaces on port 8000 so clients on the local VPN can reach it. SQLite and the env file live under `/mnt/library/keel-data/`, outside the git checkout.

| Variable | Production value |
| --- | --- |
| `KEEL_HOST` | `0.0.0.0` |
| `KEEL_PORT` | `8000` |
| `KEEL_RELOAD` | `false` |
| `KEEL_LOG_LEVEL` | `info` |
| `KEEL_DATABASE_URL` | `sqlite+pysqlite:////mnt/library/keel-data/keel.db` |

Those keys are in [`deploy/keel.env.example`](deploy/keel.env.example). Bootstrap copies them to `/mnt/library/keel-data/keel.env` if that file is missing and does not overwrite an existing file. `KEEL_DEFAULT_USER` is left unset so the service account's OS username is used.

One-time setup on the Pi (Python 3.12, venv, data directory, linger, enable the unit):

```bash
./scripts/bootstrap-prod.sh
```

Later updates are [`scripts/deploy-prod.sh`](scripts/deploy-prod.sh), invoked by the Deploy workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) after CI on `main` succeeds. Do not put VPN hostnames or addresses in this repository.

## Lint and test

```powershell
poe check
```

That runs [pre-commit](https://pre-commit.com/) on all files, including isort, mypy, and the full pytest run with 90% coverage. Hooks also run on `git commit` after onboarding. Re-run `poe hooks` to reinstall git hooks and refresh hook environments.

Tests are grouped under `tests/`:

| Suite | Directory | Poe task |
| --- | --- | --- |
| Unit | `tests/unit/` | `poe test-unit` |
| Integration | `tests/integration/` | `poe test-integration` |
| System | `tests/system/` | `poe test-system` |
| All | `tests/` | `poe test` (must pass; **90%** coverage of `keel`) |

Add further suites the same way (directory + pytest marker + `poe test-<name>` task). Markers are applied from the directory name (`unit`, `integration`, `system`).

Individual tasks: `poe lint`, `poe format`, `poe format-check`, `poe isort`, `poe isort-check`, `poe mypy`, `poe pre-commit`, `poe test`. Run `poe` with no arguments to list them.

## Documentation

What Keel is and why is described in the [architecture package](docs/architecture/context.md); how it is built is described in the design package and the decision records.

| Area | Documents |
| --- | --- |
| Architecture | [Context](docs/architecture/context.md), [use cases](docs/architecture/use-cases.md), [domain model](docs/architecture/domain-model.md), [capabilities](docs/architecture/capabilities.md), [v1 scope](docs/architecture/v1-scope.md), [glossary](docs/architecture/glossary.md) |
| Design | [Data model](docs/design/data-model.md), [API reference](docs/design/api.md), [module layout](docs/design/module-layout.md), [UI design](docs/design/ui.md), [implementation plan](docs/design/implementation-plan.md) |
| Decisions | [ADRs](docs/adr/) — 001 and 002 cover the web chrome, 003 to 006 the domain, 007 to 025 the implementation, [026](docs/adr/ADR-026.md) production deploy |
| Other | [Brand colors](docs/brand-colors.md), [package version](docs/version.md) |

The [implementation plan](docs/design/implementation-plan.md) is the build order. All six v1 phases are in place.

## License

This is not an open-source project. See [LICENSE](LICENSE) or the in-app page at `/license`.
