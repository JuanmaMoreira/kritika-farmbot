"""Measure Character Select scroll transitions without selecting a character."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.action_executor import (
    ActionExecutor,
)
from bot.adb import AdbError
from bot.capture import CaptureError, FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.observed_scroll import (
    ObservedScroll,
    ObservedScrollConfig,
    ViewportMotionDetector,
)
from bot.config import RuntimeConfig
from bot.perception import build_default_perception
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot
from bot.semantic_actions import (
    ConfirmCharacterSelection,
    OpenCharacterSelect,
    OpenQuickMenu,
    Swipe,
)
from bot.state import ResolutionStatus


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement that this diagnostic sends scoped ADB input",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=REPOSITORY_ROOT / ".env",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--entries", type=int, default=1)
    parser.add_argument(
        "--return-to-lobby",
        action="store_true",
        help="tap Select without choosing a card and verify Lobby after each entry",
    )
    parser.add_argument("--movement-threshold", type=float, default=0.05)
    parser.add_argument("--end-confirmations", type=int, default=1)
    parser.add_argument("--scroll-x", type=float, default=0.80)
    parser.add_argument("--scroll-start-y", type=float, default=0.80)
    parser.add_argument("--scroll-end-y", type=float, default=0.025)
    parser.add_argument("--scroll-duration-ms", type=int, default=190)
    parser.add_argument("--confirmation-scroll-x", type=float, default=0.68)
    parser.add_argument(
        "--confirmation-scroll-start-y", type=float, default=0.76
    )
    parser.add_argument(
        "--confirmation-scroll-end-y", type=float, default=0.24
    )
    parser.add_argument(
        "--confirmation-scroll-duration-ms", type=int, default=200
    )
    parser.add_argument("--entry-settle-for", type=float, default=0.75)
    parser.add_argument("--post-action-settle-for", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=6.0)
    return parser.parse_args(argv)


def measure_static_control(
    observer: RuntimeObserver,
    detector: ViewportMotionDetector,
    before: RuntimeSnapshot,
    *,
    timeout: float,
    observe_for: float,
):
    """Measure the same ROI window without issuing any input."""

    samples: list[FrameSnapshot] = []

    def clean_character_select(snapshot: RuntimeSnapshot) -> bool:
        samples.append(snapshot.frame)
        return _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)

    settled = observer.wait_until(
        clean_character_select,
        after_sequence=before.sequence,
        timeout=timeout,
        abort_if=_has_incompatible_clean_screen,
        stable_for=observe_for,
    )
    return (
        settled,
        detector.measure_transition(before.frame, samples, settled.frame),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        print(
            "Refusing to send Android input without --execute. "
            "Obtain the required chat authorization first.",
            file=sys.stderr,
        )
        return 2
    if args.attempts <= 0 or args.end_confirmations <= 0 or args.entries <= 0:
        print(
            "--attempts, --entries and --end-confirmations must be positive",
            file=sys.stderr,
        )
        return 2
    if args.entries > 1 and not args.return_to_lobby:
        print("--entries greater than one requires --return-to-lobby", file=sys.stderr)
        return 2

    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        source = build_frame_source(
            config,
            adb_client=adb,
            video_bit_rate=8_000_000,
            max_fps=30,
        )
        perception = build_default_perception(REPOSITORY_ROOT)
        resolver = build_default_resolver()
        progress_swipe = Swipe(
            start=(args.scroll_x, args.scroll_start_y),
            end=(args.scroll_x, args.scroll_end_y),
            duration_ms=args.scroll_duration_ms,
        )
        confirmation_x = (
            args.scroll_x
            if args.confirmation_scroll_x is None
            else args.confirmation_scroll_x
        )
        confirmation_start_y = (
            args.scroll_start_y
            if args.confirmation_scroll_start_y is None
            else args.confirmation_scroll_start_y
        )
        confirmation_end_y = (
            args.scroll_end_y
            if args.confirmation_scroll_end_y is None
            else args.confirmation_scroll_end_y
        )
        confirmation_duration_ms = (
            args.scroll_duration_ms
            if args.confirmation_scroll_duration_ms is None
            else args.confirmation_scroll_duration_ms
        )
        confirmation_swipe = Swipe(
            start=(confirmation_x, confirmation_start_y),
            end=(confirmation_x, confirmation_end_y),
            duration_ms=confirmation_duration_ms,
        )
        scroll_config = ObservedScrollConfig(
            progress_swipe=progress_swipe,
            confirmation_swipe=confirmation_swipe,
            movement_threshold=args.movement_threshold,
            required_confirmations=args.end_confirmations,
            max_attempts=args.attempts,
            timeout=args.timeout,
            settle_for=args.post_action_settle_for,
        )
        actions = ActionExecutor(adb)
        detector = ViewportMotionDetector(
            region=(0.49, 0.19, 0.85, 0.805),
            unchanged_threshold=0.05,
        )
        with source:
            observer = RuntimeObserver(source, perception, resolver)
            observed_scroll = ObservedScroll(observer, actions)
            entry_results = []
            all_entries_passed = True
            for entry in range(1, args.entries + 1):
                print(f"entry {entry}/{args.entries}: opening Character Select", flush=True)
                current = _open_character_select(
                    observer,
                    actions,
                    timeout=args.timeout,
                    settle_for=args.entry_settle_for,
                )
                print(f"entry {entry}/{args.entries}: Character Select confirmed", flush=True)
                current, static_control = measure_static_control(
                    observer,
                    detector,
                    current,
                    timeout=args.timeout,
                    observe_for=args.post_action_settle_for,
                )
                print(
                    f"entry {entry}/{args.entries}: static control "
                    f"max_transient={static_control.max_transient_difference:.6f}, "
                    f"settled={static_control.settled_difference:.6f}, "
                    f"frames={static_control.fresh_sample_count}",
                    flush=True,
                )
                scroll_result = observed_scroll.scroll_to_edge(
                    current,
                    detector=detector,
                    config=scroll_config,
                    is_compatible=lambda snapshot: _is_clean_base(
                        snapshot, SCREEN_CHARACTER_SELECT
                    ),
                    abort_if=_has_incompatible_clean_screen,
                )
                current = scroll_result.final_snapshot
                for attempt, (measurement, kind) in enumerate(
                    zip(scroll_result.attempts, scroll_result.attempt_kinds),
                    start=1,
                ):
                    print(
                        f"entry {entry}/{args.entries}, scroll {attempt}/{args.attempts}: "
                        f"kind={kind.value}, "
                        f"max_transient={measurement.max_transient_difference:.6f}, "
                        f"settled={measurement.settled_difference:.6f}, "
                        f"frames={measurement.fresh_sample_count}",
                        flush=True,
                    )
                bottom_reached = scroll_result.edge_reached

                lobby_confirmed = False
                entry_results.append(
                    {
                        "attempts": [asdict(item) for item in scroll_result.attempts],
                        "bottom_confirmation_count": scroll_result.confirmation_count,
                        "bottom_reached": bottom_reached,
                        "classifications": [
                            kind.value for kind in scroll_result.attempt_kinds
                        ],
                        "effective_swipe_count": scroll_result.effective_gesture_count,
                        "entry": entry,
                        "lobby_confirmed": lobby_confirmed,
                        "static_control": asdict(static_control),
                    }
                )
                if not bottom_reached:
                    all_entries_passed = False
                    print(
                        f"entry {entry}/{args.entries}: bottom not confirmed; aborting",
                        file=sys.stderr,
                        flush=True,
                    )
                    break
                print(f"entry {entry}/{args.entries}: bottom confirmed", flush=True)
                if args.return_to_lobby:
                    current = _return_to_lobby(
                        observer,
                        actions,
                        current,
                        timeout=args.timeout,
                        settle_for=args.entry_settle_for,
                    )
                    entry_results[-1]["lobby_confirmed"] = True
                    print(f"entry {entry}/{args.entries}: Lobby confirmed", flush=True)
    except (AdbError, CaptureError, OSError, ValueError) as error:
        print(f"Rotation scroll diagnostic failed: {error}", file=sys.stderr)
        return 2

    payload = {
        "all_entries_passed": all_entries_passed,
        "confirmation_gesture": {
            "duration_ms": confirmation_swipe.duration_ms,
            "normalized_end": confirmation_swipe.end,
            "normalized_start": confirmation_swipe.start,
        },
        "progress_gesture": {
            "duration_ms": progress_swipe.duration_ms,
            "normalized_end": progress_swipe.end,
            "normalized_start": progress_swipe.start,
        },
        "roi": detector.region,
        "settled_similarity_reference": detector.unchanged_threshold,
        "entries": entry_results,
        "transient_movement_threshold": args.movement_threshold,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all_entries_passed and len(entry_results) == args.entries else 1


def _open_character_select(
    observer: RuntimeObserver,
    actions: ActionExecutor,
    *,
    timeout: float,
    settle_for: float,
) -> RuntimeSnapshot:
    initial = observer.observe()
    if not _is_clean_base(initial, SCREEN_LOBBY):
        raise ValueError("precondition_lobby_failed")

    actions.execute(OpenQuickMenu(), initial.geometry)
    quick_menu = observer.wait_until(
        _has_quick_menu,
        after_sequence=initial.sequence,
        timeout=timeout,
        abort_if=_has_unexpected_quick_menu_state,
    )
    actions.execute(OpenCharacterSelect(), quick_menu.geometry)
    return observer.wait_until(
        lambda snapshot: _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT),
        after_sequence=quick_menu.sequence,
        timeout=timeout,
        abort_if=_has_incompatible_character_select_transition,
        stable_for=settle_for,
    )


def _return_to_lobby(
    observer: RuntimeObserver,
    actions: ActionExecutor,
    current: RuntimeSnapshot,
    *,
    timeout: float,
    settle_for: float,
) -> RuntimeSnapshot:
    if not _is_clean_base(current, SCREEN_CHARACTER_SELECT):
        raise ValueError("precondition_character_select_failed")
    actions.execute(ConfirmCharacterSelection(), current.geometry)
    return observer.wait_until(
        lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
        after_sequence=current.sequence,
        timeout=timeout,
        abort_if=_has_incompatible_clean_screen,
        stable_for=settle_for,
    )


def _is_clean_base(snapshot: RuntimeSnapshot, base: str) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == base
        and not state.overlays
    )


def _has_quick_menu(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        set(state.overlays) == {MENU_QUICK}
        and (
            state.status is ResolutionStatus.UNKNOWN
            or (
                state.status is ResolutionStatus.RESOLVED
                and state.base_context == SCREEN_LOBBY
            )
        )
    )


def _has_unexpected_quick_menu_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(set(state.overlays) - {MENU_QUICK})
    )


def _has_incompatible_character_select_transition(
    snapshot: RuntimeSnapshot,
) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(set(state.overlays) - {MENU_QUICK})
    )


def _has_incompatible_clean_screen(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or bool(snapshot.state.overlays)
    )


if __name__ == "__main__":
    raise SystemExit(main())
