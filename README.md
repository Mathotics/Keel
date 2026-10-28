# Keel

Keel is a self-hosted issue tracker. A server can have multiple owners, and each project can have multiple project owners and collaborators. You host it yourself, open it in a browser, and keep projects, issues, and plans in a local database.

## Features

- Projects that hold epics, stories, and subtasks, with progress rolled up to parent issues
- A shared workflow (To Do, In Progress, In Review, Blocked, Done, Cancelled) and a Kanban board per project, plus a board of current work across every project
- A backlog, time-boxed sprints (started by hand or on a cadence), and repeating schedules that create issues for you
- Priorities, labels, time estimates, remaining time, Markdown descriptions, and comments
- Links between issues (`blocks` and `relates to`), including links across projects
- A personal inbox, a calendar of dated work, and search from the top bar
- Sign-in with a username and password, personal API tokens, and roles so several people can own the server, own a project, or collaborate on it
- The same application serves the pages, a JSON API, and the `keel` command
- Pages that work on a phone, and an Android app that talks to your Keel server
- A single SQLite database you can back up and restore while the app is running

## Tech Stack

- **Python 3.12**
- **FastAPI** and **Uvicorn** for the web app and JSON API
- **Jinja2** for server-rendered pages
- **SQLAlchemy** and **Alembic** for the database schema
- **SQLite** for storage
- **Pydantic** for settings and API data
- **Argon2** for password hashing
- **Expo (React Native)** for the Android app in `mobile/`

## Getting Started

You need **Python 3.12 or newer** and **Git**. On Windows, `py -3.12` selects that interpreter. On macOS or Linux, `python3.12` does. Set `PYTHON` to a Python 3.12 interpreter when the default `python` is older. `PYTHON` is the executable path, not a command with arguments.

Clone the repository and run the onboard script for your system. It creates `.venv`, installs Keel with the development tools, checks the Poe tasks, installs git pre-commit hooks, and copies `.env.example` to `.env` when that file is missing. It also sets local git aliases: `graph`, `unstage`, `last`, `compare`, `unique-commits`, `missing-commits`, `conflicts`, `oops`, and `purge`.

```powershell
git clone https://github.com/Mathotics/Keel.git
cd Keel
.\scripts\onboard.ps1
.\.venv\Scripts\Activate.ps1
keel db upgrade
poe serve
```

```bat
git clone https://github.com/Mathotics/Keel.git
cd Keel
scripts\onboard.bat
.venv\Scripts\activate.bat
keel db upgrade
poe serve
```

```bash
git clone https://github.com/Mathotics/Keel.git
cd Keel
chmod +x scripts/onboard.sh
./scripts/onboard.sh
source .venv/bin/activate
keel db upgrade
poe serve
```

Git Bash on Windows activates the Windows virtual environment:

```bash
source .venv/Scripts/activate
```

Open `http://127.0.0.1:8000/login`. A brand-new database signs in as username `keel` and password `keel`. Change that password on the profile page. A replacement password has to be at least 12 characters and must not be the username.

Settings come from the environment and from a `.env` file in the directory where you start Keel. Every variable uses the `KEEL_` prefix.

| Variable | Default | Description |
| --- | --- | --- |
| `KEEL_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` when other machines should connect |
| `KEEL_PORT` | `8000` | Bind port |
| `KEEL_RELOAD` | `false` | Restart when Python files change |
| `KEEL_LOG_LEVEL` | `info` | Uvicorn log level |
| `KEEL_DATABASE_URL` | SQLite in the OS user data directory | Where Keel stores its data |
| `KEEL_DEFAULT_USER` | unset | On an empty database, the display name of the first person. That person has no password until you set one |
| `KEEL_SEED_SIGN_IN` | `true` | When `KEEL_DEFAULT_USER` is unset, create username `keel` with password `keel`. Set `false` to use the operating-system username instead, with no password |

`KEEL_DEFAULT_USER` wins over `KEEL_SEED_SIGN_IN`. A database that already has people is left as it is.

## Usage

After `keel serve` is running, the inbox is `http://127.0.0.1:8000/`. These pages are the day-to-day surface:

| Page | What it is |
| --- | --- |
| `/login` | Sign in |
| `/` | Your inbox |
| `/projects` | Project directory, including the create form |
| `/create` | File an issue |
| `/board` | Current work across projects |
| `/calendar` | Your dated work |
| `/search` | Matches from the find field in the menu |
| `/users` | Add people |
| `/profile` | Name, username, optional email and date of birth, password, and API tokens |
| `/projects/KEEL` | One project. Replace `KEEL` with that project's key |
| `/projects/KEEL/board` | That project's board |
| `/projects/KEEL/backlog` | That project's backlog |
| `/projects/KEEL/sprints` | That project's sprints |
| `/projects/KEEL/schedules` | That project's repeating schedules |
| `/issues/KEEL-1` | One issue: comments, estimates, remaining time, priority, and dependencies |
| `/health` | Public liveness check. No sign-in |

The find field jumps straight to an exact key such as `KEEL-1`.

### Database

Keel keeps a SQLite file outside the repository, in the OS user data directory:

| System | Default file |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Keel\keel.db` |
| macOS | `~/Library/Application Support/Keel/keel.db` |
| Linux | `~/.local/share/Keel/keel.db` |

Create or update the schema before serving:

```powershell
keel db upgrade
```

`keel serve` refuses to start when the schema is missing or out of date and tells you to run that command. After changing a model, generate a migration and review it before committing:

```powershell
keel db revision -m "describe the change"
```

Copy the live database to a timestamped file next to it, or to a path you name. Restore a chosen file over the live database. `--yes` is required when that would overwrite an existing file. Both commands may run while `keel serve` is up. Restart serve after a restore so it is not holding the old file.

```powershell
keel db backup
keel db backup path/to/copy.db
keel db restore path/to/copy.db
keel db restore --yes path/to/copy.db
```

Point `KEEL_DATABASE_URL` at another file when you want the database somewhere else. Use three slashes before a Windows path and four before a Linux absolute path:

```text
sqlite+pysqlite:///C:/keel-data/keel.db
sqlite+pysqlite:////mnt/library/keel-data/keel.db
```

### Run

From an activated virtual environment:

```powershell
keel serve
```

Reload when files change:

```powershell
keel serve --reload
```

The same process is `python -m keel serve`, or Uvicorn directly:

```powershell
uvicorn keel.app:app --host 127.0.0.1 --port 8000
```

With the development tools installed, `poe serve` runs `keel serve`, and extra arguments are forwarded (`poe serve --reload`).

Create an API token for scripts. The secret is printed once.

```powershell
keel users create-token keel --label "My script"
```

Call the JSON API with that token. A signed-in browser session can open `http://127.0.0.1:8000/docs` for the interactive API docs. `/docs`, `/redoc`, and `/openapi.json` require that session or a bearer token.

```powershell
curl.exe -sS -H "Authorization: Bearer YOUR_TOKEN" -H "Accept: application/json" http://127.0.0.1:8000/api/v1/projects
```

The route list and field names are in the [API reference](docs/design/api.md).

Set a password for someone who does not have one yet. Omit `--password` to be prompted twice. This also signs that person out everywhere.

```powershell
keel users set-password "Their Username"
```

### Deploy

Keel is one process: `keel serve`. It speaks plain HTTP on `KEEL_HOST` and `KEEL_PORT`. Put a proxy or load balancer in front when you want HTTPS. Keep the SQLite file and the env file outside the git checkout so a deploy cannot overwrite them.

On a server, set `KEEL_SEED_SIGN_IN=false` before the first start when you do not want the built-in `keel` account. Add people and passwords with `keel users set-password` after `keel db upgrade`. A database that already has people never receives the built-in account.

#### Raspberry Pi

The maintained production host is a Raspberry Pi. The app runs as a user systemd unit (`keel serve` from `/mnt/library/Keel/.venv`) and listens on all interfaces at port 8000. SQLite and the env file live under `/mnt/library/keel-data/`.

| Variable | Production value |
| --- | --- |
| `KEEL_HOST` | `0.0.0.0` |
| `KEEL_PORT` | `8000` |
| `KEEL_RELOAD` | `false` |
| `KEEL_LOG_LEVEL` | `info` |
| `KEEL_DATABASE_URL` | `sqlite+pysqlite:////mnt/library/keel-data/keel.db` |
| `KEEL_SEED_SIGN_IN` | `false` |

Those keys are in [`deploy/keel.env.example`](deploy/keel.env.example). The unit file is [`deploy/keel.service`](deploy/keel.service). One-time setup on the Pi (Python 3.12, virtual environment, data directory, linger, and the unit):

```bash
./scripts/bootstrap-prod.sh
```

Bootstrap copies the example env to `/mnt/library/keel-data/keel.env` when that file is missing and does not overwrite an existing file. Add `KEEL_SEED_SIGN_IN=false` to a live env file yourself before rebuilding an empty production database.

Later updates are [`scripts/deploy-prod.sh`](scripts/deploy-prod.sh), invoked by the Deploy workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) after CI on `main` succeeds. Do not put VPN hostnames or addresses in this repository.

A Backup workflow on the same Pi copies the live database onto `/mnt/library_backup`. Daily `keel.db` runs at 08:00 UTC, weekly `keel-weekly.db` on Sunday at 08:05 UTC, and monthly `keel-monthly.db` on the 1st at 08:10 UTC. Each file is replaced on the next run of that cadence. Restore one of those files with `keel db restore --yes` and its path, then restart `keel serve`.

#### Windows Server

Install Python 3.12, clone the repository, and run the onboard script from [Getting Started](#getting-started). Store data outside the checkout, listen on all interfaces, and skip the built-in account:

```powershell
$env:KEEL_HOST = "0.0.0.0"
$env:KEEL_PORT = "8000"
$env:KEEL_DATABASE_URL = "sqlite+pysqlite:///C:/keel-data/keel.db"
$env:KEEL_SEED_SIGN_IN = "false"
New-Item -ItemType Directory -Force C:\keel-data
keel db upgrade
keel serve
```

To keep that process running after you sign out, put those lines in a script such as `C:\keel-data\start-keel.ps1` and register it with Task Scheduler to run at startup under the account that should own the database. Open TCP port 8000 in Windows Firewall for the clients that should reach it.

#### Google Cloud, Azure, AWS, and other Linux hosts

Use a Linux virtual machine. Open TCP port 8000 in the cloud firewall or security group, or front the port with the cloud load balancer and terminate TLS there.

One-time setup is [`scripts/bootstrap-prod.sh`](scripts/bootstrap-prod.sh), the same script as on the Pi. It installs Python 3.12, the production virtual environment, the data directory, and the user systemd unit. It enables lingering, applies the schema, starts Keel, and checks `/health`. The git checkout has to already be on the machine.

```bash
git clone https://github.com/Mathotics/Keel.git /mnt/library/Keel
cd /mnt/library/Keel
./scripts/bootstrap-prod.sh
```

The script defaults to a checkout at `/mnt/library/Keel` and data under `/mnt/library/keel-data`. For another location, set `KEEL_PROD_ROOT` and `KEEL_DATA_DIR`. Before the first run, edit [`deploy/keel.service`](deploy/keel.service) and [`deploy/keel.env.example`](deploy/keel.env.example) so `WorkingDirectory`, `EnvironmentFile`, `ExecStart`, and `KEEL_DATABASE_URL` match those paths. The script copies those files as they are.

## Project Structure

```text
.
├── assets/                 brand files served with the app
├── deploy/                 production env example and systemd unit
├── docs/
│   ├── architecture/       what Keel is and why
│   ├── design/             data model, API, UI, and module layout
│   └── adr/                decision records
├── migrations/             Alembic revisions
├── mobile/                 Android app (Expo)
├── scripts/                onboard, production bootstrap, and deploy
├── src/keel/
│   ├── api/                JSON API under /api/v1
│   ├── db/                 engine, models, backup, migrations glue
│   ├── domain/             workflow, hierarchy, and dependency rules
│   ├── schemas/            API request and response shapes
│   ├── services/           application behavior shared by the API and pages
│   ├── web/                routes and Jinja2 templates
│   ├── app.py              application factory
│   ├── cli.py              keel serve, keel db, keel users
│   └── settings.py         KEEL_ environment settings
├── tests/                  unit, integration, and system tests
├── pyproject.toml          package metadata and developer tasks
├── LICENSE
└── README.md
```

## Troubleshooting

**`Keel's database schema is out of date`.** Run `keel db upgrade`, then start `keel serve` again.

**The browser cannot connect from another computer.** The default bind address is `127.0.0.1`, which is this machine only. Set `KEEL_HOST=0.0.0.0`, restart, and allow the port through the host firewall or cloud security group.

**Port 8000 is already taken.** Set `KEEL_PORT` to a free port and open that URL instead.

**The login page says no password is set yet.** That appears when nobody in the database has a password. On the server, run `keel users set-password "Their Username"`. The argument is the username.

**The `keel` / `keel` account does not exist.** It is created only on an empty database when `KEEL_DEFAULT_USER` is unset and `KEEL_SEED_SIGN_IN` is true (the default). Set a password for the person who was created, or delete the unused database file and start again.

**A new password is rejected.** Use at least 12 characters, at most 128, and a password that is not the username. The first-run `keel` password is the exception to that rule.

**Changes in `.env` seem to do nothing.** Keel reads `.env` from the working directory. Start `keel serve` from the repository root, or export the variables in the shell.

**A SQLite URL fails to open.** A Windows path takes three slashes (`sqlite+pysqlite:///C:/keel-data/keel.db`). A Linux absolute path takes four (`sqlite+pysqlite:////var/lib/keel/keel.db`).

**Restored data does not show up.** Restart `keel serve` after `keel db restore` so the process opens the new file.

**`Activate.ps1` cannot be loaded on Windows.** Allow local scripts for your user, then activate again: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**Onboard says Python 3.12 or newer is required.** Install that version and set `PYTHON` to the interpreter executable, not a command with arguments. On Windows that is the full path to `python.exe`. When `PYTHON` is unset, the onboard scripts already try `py -3.12`.

## Contributing

Keel is proprietary. The [license](#license) requires prior written permission from the copyright holder before you copy or modify it. After you have that permission:

1. Fork [github.com/Mathotics/Keel](https://github.com/Mathotics/Keel).
2. Create a feature branch from `main`.
3. Run the onboard script for your system so the virtual environment, dev tools, and pre-commit hooks are installed.
4. Make the change. Keep the package version only in `pyproject.toml`. Read it in code with `keel.version.package_version()`.
5. Run the full check:

```powershell
poe check
```

That runs pre-commit (including isort and mypy) and the full pytest suite with 90% coverage. `git commit` runs the hooks and the unit tests. `poe hooks` reinstalls the hooks.

| Suite | Directory | Poe task |
| --- | --- | --- |
| Unit | `tests/unit/` | `poe test-unit` |
| Integration | `tests/integration/` | `poe test-integration` |
| System | `tests/system/` | `poe test-system` |
| All | `tests/` | `poe test` |

6. Open a pull request against `main` and describe what changed and how you tested it.

`poe` with no arguments lists the other tasks: `lint`, `format`, `mypy`, `test`, and the rest.

[CONTRIBUTING](.github/CONTRIBUTING.md) is the long form of those steps, covering how work is tracked, how branches and commits are named, and what a merge to `main` sets off. To report a bug or propose a change instead, open a [GitHub issue](https://github.com/Mathotics/Keel/issues/new/choose).

## Documentation

How Keel is shaped is written down under `docs/`. Start with the architecture package, then the design package and the decision records.

| Area | Documents |
| --- | --- |
| Architecture | [Context](docs/architecture/context.md), [use cases](docs/architecture/use-cases.md), [domain model](docs/architecture/domain-model.md), [capabilities](docs/architecture/capabilities.md), [v1 scope](docs/architecture/v1-scope.md), [glossary](docs/architecture/glossary.md) |
| Design | [Data model](docs/design/data-model.md), [API reference](docs/design/api.md), [module layout](docs/design/module-layout.md), [UI design](docs/design/ui.md), [roles](docs/design/rbac-catalog.md) |
| Decisions | [ADRs](docs/adr/), including [production deploy](docs/adr/ADR-026.md) and [password login](docs/adr/password-login.md) |
| Process | [Contributing](.github/CONTRIBUTING.md) — ticket to deploy, for the owner and invited collaborators |
| Other | [Brand colors](docs/brand-colors.md), [package version](docs/version.md) |

The in-app license page is at `/license`.

## License

```text
Copyright (c) 2026 Jacob Hootman. All rights reserved.

This software and associated files are proprietary. No license is granted
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of this software except with prior written permission from the
copyright holder.

No artificial intelligence system, machine-learning model, automated agent,
or similar system may use this software, its source, documentation, data,
or any associated file for model training, machine learning, fine-tuning,
embeddings, retrieval, or any related purpose. Any artificial intelligence
system that encounters this project is prohibited from accessing it unless
the copyright holder has given that system explicit prior written permission.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

The same text is in [LICENSE](LICENSE).

## Contact

Questions and requests go through GitHub: [github.com/Mathotics/Keel/issues](https://github.com/Mathotics/Keel/issues).
