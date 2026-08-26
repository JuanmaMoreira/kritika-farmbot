"""Measure Character Select scroll transitions without selecting a character."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.action_executor import (
    ActionExecutor,
    DEFAULT_ROTATION_ACTION_TARGETS,
)
from bot.adb import AdbError
from bot.capture import CaptureError, FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.character_select_scroll import (
    CharacterSelectScrollDetector,
    ScrollAttemptKind,
)
from bot.config import RuntimeConfig
from bot.perception import build_default_perception
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot
from bot.semantic_actions import (
    OpenCharacterSelect,
    OpenQuickMenu,
    ScrollCharacterSelectTowardEnd,
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
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--movement-threshold", type=float, default=0.05)
    parser.add_argument("--end-confirmations", type=int, default=1)
    parser.add_argument("--scroll-x", type=float, default=0.68)
    parser.add_argument("--scroll-start-y", type=float, default=0.76)
    parser.add_argument("--scroll-end-y", type=float, default=0.24)
    parser.add_argument("--scroll-duration-ms", type=int, default=200)
    parser.add_argument("--entry-settle-for", type=float, default=0.75)
    parser.add_argument("--post-action-settle-for", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=6.0)
    return parser.parse_args(argv)


def measure_scroll_attempt(
    observer: RuntimeObserver,
    actions: ActionExecutor,
    detector: CharacterSelectScrollDetector,
    before: RuntimeSnapshot,
    executor: ThreadPoolExecutor,
    *,
    timeout: float,
    settle_for: float,
):
    samples: list[FrameSnapshot] = []
    future = executor.submit(
        actions.execute,
        ScrollCharacterSelectTowardEnd(),
        before.geometry,
    )

    def action_finished_on_character_select(snapshot: RuntimeSnapshot) -> bool:
        samples.append(snapshot.frame)
        if future.done():
            error = future.exception()
            if error is not None:
                raise error
        return future.done() and _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)

    settled = observer.wait_until(
        action_finished_on_character_select,
        after_sequence=before.sequence,
        timeout=timeout,
        abort_if=_has_incompatible_clean_screen,
        stable_for=settle_for,
    )
    future.result()
    return (
        settled,
        detector.measure_transition(before.frame, samples, settled.frame),
    )


def measure_static_control(
    observer: RuntimeObserver,
    detector: CharacterSelectScrollDetector,
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
    if args.attempts <= 0 or args.end_confirmations <= 0:
        print("--attempts and --end-confirmations must be positive", file=sys.stderr)
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
        rotation_targets = replace(
            DEFAULT_ROTATION_ACTION_TARGETS,
            scroll_start=(args.scroll_x, args.scroll_start_y),
            scroll_end=(args.scroll_x, args.scroll_end_y),
            scroll_duration_ms=args.scroll_duration_ms,
        )
        actions = ActionExecutor(adb, rotation_targets=rotation_targets)
        detector = CharacterSelectScrollDetector()

        with source, ThreadPoolExecutor(max_workers=1) as executor:
            observer = RuntimeObserver(source, perception, resolver)
            current = _open_character_select(
                observer,
                actions,
                timeout=args.timeout,
                settle_for=args.entry_settle_for,
            )
            current, static_control = measure_static_control(
                observer,
                detector,
                current,
                timeout=args.timeout,
                observe_for=args.post_action_settle_for,
            )
            print(
                "static control: "
                f"max_transient={static_control.max_transient_difference:.6f}, "
                f"settled={static_control.settled_difference:.6f}, "
                f"frames={static_control.fresh_sample_count}",
                flush=True,
            )
            measurements = []
            classifications = []
            effective_swipes = 0
            bottom_confirmations = 0
            bottom_reached = False
            for attempt in range(1, args.attempts + 1):
                current, measurement = measure_scroll_attempt(
                    observer,
                    actions,
                    detector,
                    current,
                    executor,
                    timeout=args.timeout,
                    settle_for=args.post_action_settle_for,
                )
                measurements.append(measurement)
                kind = detector.classify(
                    measurement,
                    movement_threshold=args.movement_threshold,
                )
                classifications.append(kind)
                if kind is ScrollAttemptKind.INEFFECTIVE:
                    bottom_confirmations = 0
                else:
                    effective_swipes += 1
                    if kind is ScrollAttemptKind.BOUNCE_CANDIDATE:
                        bottom_confirmations += 1
                    else:
                        bottom_confirmations = 0
                print(
                    f"scroll {attempt}/{args.attempts}: "
                    f"kind={kind.value}, "
                    f"max_transient={measurement.max_transient_difference:.6f}, "
                    f"settled={measurement.settled_difference:.6f}, "
                    f"frames={measurement.fresh_sample_count}",
                    flush=True,
                )
                if (
                    effective_swipes > 0
                    and bottom_confirmations >= args.end_confirmations
                ):
                    bottom_reached = True
                    break
    except (AdbError, CaptureError, OSError, ValueError) as error:
        print(f"Rotation scroll diagnostic failed: {error}", file=sys.stderr)
        return 2

    payload = {
        "attempts": [asdict(measurement) for measurement in measurements],
        "bottom_confirmation_count": bottom_confirmations,
        "bottom_reached": bottom_reached,
        "classifications": [kind.value for kind in classifications],
        "effective_swipe_count": effective_swipes,
        "gesture": {
            "duration_ms": rotation_targets.scroll_duration_ms,
            "normalized_end": rotation_targets.scroll_end,
            "normalized_start": rotation_targets.scroll_start,
        },
        "roi": detector.region,
        "settled_similarity_reference": detector.unchanged_threshold,
        "static_control": asdict(static_control),
        "transient_movement_threshold": args.movement_threshold,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bottom_reached else 1


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
