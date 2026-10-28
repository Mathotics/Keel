# Contributing to Keel

Keel is proprietary and closed to the public. Only the copyright holder and the collaborators he has invited may contribute; see [LICENSE](../LICENSE). If you are not one of them, do not open a pull request.

This guide is the checklist for a change from ticket to production. [README](../README.md) covers what Keel is and how to run it.

## Where work comes from

Keel tracks its own work. Every change starts from an item in the **KEEL** project of the running Keel instance, not from a GitHub issue. GitHub issues are not used.

If the work does not have an item yet, file one first so the branch, the commits, and the pull request can all name the same key.

## Set up a checkout

Run the onboarding script for your shell once per checkout. It creates `.venv`, installs the package in editable mode with the `dev` extra, installs the git hooks, and copies `.env.example` to `.env`.

```powershell
.\scripts\onboard.ps1
.\.venv\Scripts\Activate.ps1
```

```bash
./scripts/onboard.sh
source .venv/bin/activate
```

Then bring the local database up to the current schema. `keel serve` refuses to start against an out-of-date one.

```powershell
keel db upgrade
```

## Branch

Branch from `main` and name the branch after the Keel key, for example `KEEL-45`. One ticket per branch.

[`scripts/deploy-worktree.ps1`](../scripts/deploy-worktree.ps1) (and the `.bat` and `.sh` siblings) creates the branch as a git worktree and onboards it in one step, which keeps the main checkout free:

```powershell
.\scripts\deploy-worktree.ps1 KEEL-45
```

## Make the change

A few rules hold across the codebase:

- **Version number.** `[project].version` in [`pyproject.toml`](../pyproject.toml) is the only place the version is written. Read it at runtime through `keel.version.package_version()`; never copy the literal into Python, templates, tests, or docs. See [package version](../docs/version.md) and [ADR 002](../docs/adr/persistent-version-footer.md).
- **Schema changes.** After editing a model, generate the migration with `keel db revision -m "describe the change"` and read the generated file before committing it.
- **Secrets.** `.env`, API tokens, database files, and signing keystores stay out of git. They are in [`.gitignore`](../.gitignore) for a reason.
- **Behavior decisions.** A change that settles how Keel behaves belongs in an ADR under [`docs/adr/`](../docs/adr/) alongside the code, and the architecture and design documents it affects should move with it.

## Check before you push

```powershell
poe check
```

That runs every pre-commit hook over all files — Ruff, isort, mypy, and the unit tests — then the full pytest run, which must hold **90%** coverage of `keel`. `git commit` runs the hooks without the full suite, so a green commit is not yet a green `poe check`.

Tests are grouped by suite, and the pytest marker comes from the directory name:

| Suite | Directory | Task |
| --- | --- | --- |
| Unit | `tests/unit/` | `poe test-unit` |
| Integration | `tests/integration/` | `poe test-integration` |
| System | `tests/system/` | `poe test-system` |
| All | `tests/` | `poe test` |

## Commit

Write the subject as a sentence that says what the change does and why it was worth doing, starting with the Keel key:

```
KEEL-45 Add a contribution guide and pull request template so a change has one checklist from ticket to deploy.
```

## Open the pull request

Push the branch and open a pull request against `main`. [The template](PULL_REQUEST_TEMPLATE.md) fills itself in; keep the sections that apply and delete the rest.

CI ([`.github/workflows/ci.yml`](workflows/ci.yml)) runs `poe check` on Python 3.12 for every pull request and has to pass before merge.

**Merging to `main` deploys.** Every push to `main` that passes CI updates the production Raspberry Pi with no further step ([ADR 026](../docs/adr/ADR-026.md)). Treat a merge as a release: the schema migration has to be safe against the live database, and nothing half-finished should land.

After the merge, move the Keel item to its finished status.
