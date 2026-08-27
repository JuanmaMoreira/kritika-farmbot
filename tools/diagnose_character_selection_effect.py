"""Verify one last-card selection and stop before pressing Select."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.action_executor import ActionExecutor
from bot.adb import AdbError
from bot.capture import CaptureError
from bot.catalog import (
    MENU_QUICK,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.character_select_scroll import DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE
from bot.character_selection import (
    CharacterSelectionState,
    DEFAULT_CHARACTER_SELECTION_DETECTOR,
)
from bot.config import RuntimeConfig
from bot.observed_scroll import ObservedScroll
from bot.perception import build_default_perception
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot
from bot.semantic_actions import (
    OpenCharacterSelect,
    OpenQuickMenu,
    SelectLastVisibleCharacter,
)
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement that scoped navigation and tap are sent",
    )
    parser.add_argument("--dotenv", type=Path, default=REPOSITORY_ROOT / ".env")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--selection-timeout", type=float, default=1.0)
    parser.add_argument("--selection-grace", type=float, default=0.75)
    parser.add_argument("--selection-attempts", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        print("Refusing to send Android input without --execute", file=sys.stderr)
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
        actions = ActionExecutor(adb)
        transition_policy = VerifiedTransitionPolicy(
            normal_timeout=args.timeout,
            grace_timeout=2.0,
            max_attempts=2,
        )
        selection_policy = VerifiedTransitionPolicy(
            normal_timeout=args.selection_timeout,
            grace_timeout=args.selection_grace,
            max_attempts=args.selection_attempts,
        )
        detector = DEFAULT_CHARACTER_SELECTION_DETECTOR

        with source:
            observer = RuntimeObserver(source, perception, resolver)
            verified = VerifiedTransition(observer, actions)
            initial = observer.observe()
            quick = verified.execute(
                "diagnostic.open_quick_menu",
                OpenQuickMenu(),
                initial,
                expected=_has_quick_menu,
                precondition=lambda item: _is_clean_base(item, SCREEN_LOBBY),
                retryable_from=lambda item: _is_clean_base(item, SCREEN_LOBBY),
                policy=transition_policy,
            )
            if not quick.succeeded:
                raise RuntimeError(f"quick_menu_failed: {quick.outcome.value}")
            character_select = verified.execute(
                "diagnostic.open_character_select",
                OpenCharacterSelect(),
                quick.final_snapshot,
                expected=lambda item: _is_clean_base(
                    item, SCREEN_CHARACTER_SELECT
                ),
                precondition=_has_quick_menu,
                retryable_from=_has_quick_menu,
                stable_for=DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE.settle_for,
                policy=transition_policy,
            )
            if not character_select.succeeded:
                raise RuntimeError(
                    "character_select_failed: "
                    f"{character_select.outcome.value}"
                )
            scroll = ObservedScroll(observer, actions).scroll_to_edge(
                character_select.final_snapshot,
                detector=DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE.detector(),
                config=DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE.config(),
                is_compatible=lambda item: _is_clean_base(
                    item, SCREEN_CHARACTER_SELECT
                ),
                abort_if=_has_incompatible_screen,
            )
            if not scroll.edge_reached:
                raise RuntimeError(f"scroll_failed: {scroll.outcome.value}")

            selection = verified.execute(
                "diagnostic.select_last_visible_character",
                SelectLastVisibleCharacter(),
                scroll.final_snapshot,
                expected=lambda item: (
                    _is_clean_base(item, SCREEN_CHARACTER_SELECT)
                    and detector.measure(item.frame).state
                    is CharacterSelectionState.SELECTED
                ),
                precondition=lambda item: (
                    _is_clean_base(item, SCREEN_CHARACTER_SELECT)
                    and detector.measure(item.frame).state
                    is CharacterSelectionState.UNSELECTED
                ),
                retryable_from=lambda item: (
                    _is_clean_base(item, SCREEN_CHARACTER_SELECT)
                    and detector.measure(item.frame).state
                    is CharacterSelectionState.UNSELECTED
                ),
                abort_if=_has_unexpected_character_select_state,
                stable_for=0.25,
                policy=selection_policy,
            )
            reading = detector.measure(selection.final_snapshot.frame)
    except (AdbError, CaptureError, OSError, RuntimeError, ValueError) as error:
        print(f"Character selection diagnostic failed: {error}", file=sys.stderr)
        return 2

    payload = {
        "bottom_reached": scroll.edge_reached,
        "scroll_attempts": [asdict(item) for item in scroll.attempts],
        "scroll_kinds": [item.value for item in scroll.attempt_kinds],
        "selection": {
            "attempt_count": selection.attempt_count,
            "grace_wait_count": selection.grace_wait_count,
            "outcome": selection.outcome.value,
            "state": reading.state.value,
            "yellow_border_ratio": reading.yellow_border_ratio,
        },
        "stopped_before_select": True,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if selection.succeeded else 1


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


def _has_incompatible_screen(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or bool(snapshot.state.overlays)
    )


def _has_unexpected_character_select_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        _has_incompatible_screen(snapshot)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_CHARACTER_SELECT
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
