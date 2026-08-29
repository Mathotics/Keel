import argparse
import sys
from collections.abc import Sequence

import uvicorn

from keel.settings import get_settings


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
    return parser


def serve(args: argparse.Namespace) -> int:
    settings = get_settings()
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "serve":
        return serve(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
