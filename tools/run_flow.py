"""Run one productive flow once on the active character."""

from __future__ import annotations

import argparse
from pathlib import Path

from bot.flow_contracts import FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.productive_runtime import (
    PROJECT_ROOT,
    CancellationToken,
    default_log_path,
    open_productive_runtime,
)
from tools.runtime_cli import (
    EXIT_CANCELLED,
    EXIT_COMPLETED,
    EXIT_FAILED,
    EXIT_USAGE_OR_RUNTIME,
    cancellation_signals,
    flow_summary,
    print_error,
    print_flows,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flow", nargs="?")
    parser.add_argument("--list-flows", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    args = parser.parse_args(argv)
    if not args.list_flows and args.flow is None:
        parser.error("a flow id is required unless --list-flows is used")
    if args.flow is not None:
        try:
            DEFAULT_FLOW_REGISTRY.get(args.flow)
        except KeyError as error:
            parser.error(str(error).strip("'"))
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list_flows:
        print_flows()
        return EXIT_COMPLETED
    definition = DEFAULT_FLOW_REGISTRY.get(args.flow)
    log_path = default_log_path(f"flow_{definition.id}", directory=args.log_dir)
    token = CancellationToken()
    try:
        with cancellation_signals(token):
            with open_productive_runtime(
                dotenv_path=args.dotenv,
                log_path=log_path,
                debug=args.debug,
                cancel_token=token,
            ) as runtime:
                result = runtime.run_flow(definition)
    except KeyboardInterrupt:
        token.request()
        print(f"result=CANCELLED log={log_path}")
        return EXIT_CANCELLED
    except Exception as error:
        print_error(f"Runtime error: {type(error).__name__}: {error}; log={log_path}")
        return EXIT_USAGE_OR_RUNTIME
    print(flow_summary(result, log_path))
    if result.status is FlowStatus.COMPLETED:
        return EXIT_COMPLETED
    if result.status is FlowStatus.CANCELLED:
        return EXIT_CANCELLED
    return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
