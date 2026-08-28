"""Run an ordered productive flow session across configured characters."""

from __future__ import annotations

import argparse
from pathlib import Path

from bot.config import DEFAULT_CHARACTER_COUNT
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.productive_runtime import (
    PROJECT_ROOT,
    CancellationToken,
    default_log_path,
    open_productive_runtime,
)
from bot.session import SessionStatus
from tools.runtime_cli import (
    EXIT_CANCELLED,
    EXIT_COMPLETED,
    EXIT_FAILED,
    EXIT_USAGE_OR_RUNTIME,
    cancellation_signals,
    print_error,
    print_flows,
    session_summary,
)


def _positive_character_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("characters must be a positive integer") from error
    if count <= 0:
        raise argparse.ArgumentTypeError("characters must be a positive integer")
    return count


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flows", nargs="*")
    parser.add_argument("--characters", type=_positive_character_count, default=DEFAULT_CHARACTER_COUNT)
    parser.add_argument("--list-flows", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    args = parser.parse_args(argv)
    if not args.list_flows and not args.flows:
        parser.error("at least one flow id is required unless --list-flows is used")
    for flow_id in args.flows:
        try:
            DEFAULT_FLOW_REGISTRY.get(flow_id)
        except KeyError as error:
            parser.error(str(error).strip("'"))
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list_flows:
        print_flows()
        return EXIT_COMPLETED
    definitions = DEFAULT_FLOW_REGISTRY.select(args.flows)
    log_path = default_log_path("session", directory=args.log_dir)
    token = CancellationToken()
    try:
        with cancellation_signals(token):
            with open_productive_runtime(
                dotenv_path=args.dotenv,
                log_path=log_path,
                debug=args.debug,
                cancel_token=token,
            ) as runtime:
                result = runtime.run_session(
                    definitions,
                    character_count=args.characters,
                )
    except KeyboardInterrupt:
        token.request()
        print(f"result=CANCELLED log={log_path}")
        return EXIT_CANCELLED
    except Exception as error:
        print_error(f"Runtime error: {type(error).__name__}: {error}; log={log_path}")
        return EXIT_USAGE_OR_RUNTIME
    print(session_summary(result, log_path))
    if result.status is SessionStatus.COMPLETED:
        return EXIT_COMPLETED
    if result.status is SessionStatus.CANCELLED:
        return EXIT_CANCELLED
    return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
