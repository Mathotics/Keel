import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from keel.db.backup import BackupError, backup_database, restore_database
from keel.db.engine import (
    create_db_engine,
    create_session_factory,
    database_file,
    ensure_database_directory,
)
from keel.db.models import User
from keel.db.revision import (
    alembic_config,
    create_revision,
    schema_is_current,
    upgrade_to_head,
)
from keel.domain.errors import DomainError, NotFoundError
from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.settings import KeelSettings, get_settings

STALE_SCHEMA = (
    "Keel's database schema is out of date. Run 'keel db upgrade' and try again."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keel", description="Keel development CLI")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the FastAPI app with Uvicorn")
    serve.add_argument("--host", help="Bind address (default: KEEL_HOST or 127.0.0.1)")
    serve.add_argument(
        "--port",
        type=int,
        help="Bind port (default: KEEL_PORT or 8000)",
    )
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (or set KEEL_RELOAD=true)",
    )
    serve.add_argument(
        "--log-level",
        help="Uvicorn log level (default: KEEL_LOG_LEVEL or info)",
    )

    database = subparsers.add_parser("db", help="Manage the database")
    database_commands = database.add_subparsers(dest="db_command")
    database_commands.add_parser("upgrade", help="Apply migrations up to head")
    revision = database_commands.add_parser(
        "revision",
        help="Generate a migration from model changes",
    )
    revision.add_argument("-m", "--message", required=True, help="Revision description")
    backup = database_commands.add_parser(
        "backup",
        help="Copy the live database to a file",
    )
    backup.add_argument(
        "destination",
        nargs="?",
        type=Path,
        help=(
            "Where to write the copy "
            "(default: timestamped file next to the live database)"
        ),
    )
    backup.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Overwrite the destination if it already exists",
    )
    restore = database_commands.add_parser(
        "restore",
        help="Replace the live database with a copy",
    )
    restore.add_argument("source", type=Path, help="Backup file to put back")
    restore.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Overwrite the live database if it already exists",
    )

    people = subparsers.add_parser("users", help="Manage sign-in for people")
    people_commands = people.add_subparsers(dest="users_command")
    set_password = people_commands.add_parser(
        "set-password",
        help="Set a password and sign that person out everywhere",
    )
    set_password.add_argument("username", help="Username, matched case-insensitively")
    set_password.add_argument(
        "--password",
        help="New password. Omit to be prompted twice",
    )
    create_token = people_commands.add_parser(
        "create-token",
        help="Create an API token and print the secret once",
    )
    create_token.add_argument("username", help="Username, matched case-insensitively")
    create_token.add_argument(
        "--label",
        default="API token",
        help="Label shown on the profile page",
    )
    return parser


def schema_is_stale(settings: KeelSettings) -> bool:
    url = settings.resolved_database_url()
    path = database_file(url)
    if path is not None and not path.is_file():
        return True
    engine = create_db_engine(url)
    try:
        return not schema_is_current(engine, alembic_config(url))
    except DatabaseError:
        return True
    finally:
        engine.dispose()


def serve(args: argparse.Namespace) -> int:
    settings = get_settings()
    if schema_is_stale(settings):
        print(STALE_SCHEMA, file=sys.stderr)
        return 1

    host = args.host if args.host is not None else settings.host
    port = args.port if args.port is not None else settings.port
    reload = True if args.reload else settings.reload
    log_level = args.log_level if args.log_level is not None else settings.log_level

    uvicorn.run(
        "keel.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )
    return 0


def db_upgrade() -> int:
    url = get_settings().resolved_database_url()
    ensure_database_directory(url)
    upgrade_to_head(alembic_config(url))
    print(f"Schema is up to date: {_describe(url)}")
    return 0


def db_revision(message: str) -> int:
    url = get_settings().resolved_database_url()
    ensure_database_directory(url)
    create_revision(alembic_config(url), message)
    return 0


def db_backup(destination: Path | None, overwrite: bool) -> int:
    url = get_settings().resolved_database_url()
    try:
        live, dest = backup_database(url, destination, overwrite=overwrite)
    except BackupError as error:
        print(error.message, file=sys.stderr)
        return 1
    print(f"Backed up {live} to {dest}")
    return 0


def db_restore(source: Path, overwrite: bool) -> int:
    url = get_settings().resolved_database_url()
    try:
        origin, live = restore_database(url, source, overwrite=overwrite)
    except BackupError as error:
        print(error.message, file=sys.stderr)
        return 1
    print(f"Restored {origin} to {live}")
    return 0


def _describe(url: str) -> str:
    path = database_file(url)
    return str(path) if path is not None else url


def database(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.db_command == "upgrade":
        return db_upgrade()
    if args.db_command == "revision":
        return db_revision(args.message)
    if args.db_command == "backup":
        return db_backup(args.destination, args.yes)
    if args.db_command == "restore":
        return db_restore(args.source, args.yes)
    parser.error("usage: keel db {upgrade,revision,backup,restore}")
    return 2


def _with_user_session(username: str) -> tuple[Session, Engine, User] | None:
    settings = get_settings()
    if schema_is_stale(settings):
        print(STALE_SCHEMA, file=sys.stderr)
        return None
    engine = create_db_engine(settings.resolved_database_url())
    factory = create_session_factory(engine)
    session = factory()
    try:
        user = user_service.find_by_username(session, username)
        if user is None:
            print(f"No user named {username}.", file=sys.stderr)
            session.close()
            engine.dispose()
            return None
        return session, engine, user
    except Exception:
        session.close()
        engine.dispose()
        raise


def users_set_password(username: str, password: str | None) -> int:
    if password is None:
        password = getpass.getpass("New password: ")
        again = getpass.getpass("Repeat password: ")
        if password != again:
            print("The passwords do not match.", file=sys.stderr)
            return 1
    opened = _with_user_session(username)
    if opened is None:
        return 1
    session, engine, user = opened
    login = user.username
    try:
        user_service.set_password(session, user, password)
        auth_service.revoke_sessions(session, user.id)
        session.commit()
    except DomainError as exc:
        session.rollback()
        print(exc.message, file=sys.stderr)
        return 1
    finally:
        session.close()
        engine.dispose()
    print(f"Password updated for {login}.")
    return 0


def users_create_token(username: str, label: str) -> int:
    opened = _with_user_session(username)
    if opened is None:
        return 1
    session, engine, user = opened
    login = user.username
    try:
        issued = auth_service.create_token(session, user, label)
        secret = issued.secret
        prefix = issued.row.token_prefix
        session.commit()
    except (DomainError, NotFoundError) as exc:
        session.rollback()
        print(exc.message, file=sys.stderr)
        return 1
    finally:
        session.close()
        engine.dispose()
    print(
        f"Token created for {login} ({prefix}). This is the only time it is shown.",
        file=sys.stderr,
    )
    print(secret)
    return 0


def users(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.users_command == "set-password":
        return users_set_password(args.username, args.password)
    if args.users_command == "create-token":
        return users_create_token(args.username, args.label)
    parser.error("usage: keel users {set-password,create-token}")
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "serve":
        return serve(args)
    if args.command == "db":
        return database(parser, args)
    if args.command == "users":
        return users(parser, args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
