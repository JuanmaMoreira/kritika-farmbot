from pathlib import Path

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import MENU_QUICK, SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from bot.observed_scroll import ViewportMotionDetector
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
import tools.diagnose_standard_rotation_scroll as diagnostic


def _runtime_snapshot(
    sequence,
    fill,
    base=SCREEN_CHARACTER_SELECT,
    *,
    overlays=(),
    status=ResolutionStatus.RESOLVED,
):
    image = np.full((200, 400, 3), fill, dtype=np.uint8)
    timestamp = float(sequence)
    frame = FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence)
    return RuntimeSnapshot(
        frame=frame,
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=status,
            sequence=sequence,
            timestamp=timestamp,
            base_context=base,
            overlays=overlays,
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append((action, geometry))


class Observer:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if,
        stable_for,
    ):
        assert all(item.sequence > after_sequence for item in self.snapshots)
        for item in self.snapshots:
            assert not abort_if(item)
            assert condition(item)
        return self.snapshots[-1]


class NavigationObserver:
    def __init__(self, initial, transitions):
        self.initial = initial
        self.transitions = iter(transitions)

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
        snapshot = next(self.transitions)
        assert snapshot.sequence > kwargs["after_sequence"]
        assert not kwargs["abort_if"](snapshot)
        assert condition(snapshot)
        return snapshot


def test_static_control_measures_fresh_frames_without_sending_input():
    before = _runtime_snapshot(10, 0)
    intermediate = _runtime_snapshot(11, 2)
    settled = _runtime_snapshot(12, 1)

    final, measurement = diagnostic.measure_static_control(
        Observer([intermediate, settled]),
        ViewportMotionDetector(region=(0.49, 0.19, 0.85, 0.805)),
        before,
        timeout=6.0,
        observe_for=0.75,
    )

    assert final is settled
    assert measurement.pre_sequence == 10
    assert measurement.settled_sequence == 12
    assert measurement.fresh_sample_count == 2


def test_diagnostic_defaults_describe_current_gesture_without_execution():
    args = diagnostic.parse_args([])

    assert not args.execute
    assert args.attempts == 3
    assert args.entries == 1
    assert not args.return_to_lobby
    assert args.end_confirmations == 1
    assert args.movement_threshold == 0.05
    assert (args.scroll_x, args.scroll_start_y, args.scroll_end_y) == (
        0.80,
        0.80,
        0.025,
    )
    assert args.scroll_duration_ms == 190
    assert args.confirmation_scroll_x == 0.68
    assert args.confirmation_scroll_start_y == 0.76
    assert args.confirmation_scroll_end_y == 0.24
    assert args.confirmation_scroll_duration_ms == 200


def test_diagnostic_requires_explicit_execute_acknowledgement(capsys):
    assert diagnostic.main([]) == 2
    assert "Refusing to send Android input" in capsys.readouterr().err


def test_return_to_lobby_uses_select_without_selecting_a_character():
    before = _runtime_snapshot(20, 0)
    lobby = _runtime_snapshot(21, 0, SCREEN_LOBBY)
    actions = Actions()

    final = diagnostic._return_to_lobby(
        Observer([lobby]),
        actions,
        before,
        timeout=6.0,
        settle_for=0.75,
    )

    assert final is lobby
    assert len(actions.calls) == 1
    assert type(actions.calls[0][0]).__name__ == "ConfirmCharacterSelection"


def test_open_character_select_returns_fresh_character_select_snapshot():
    lobby = _runtime_snapshot(30, 0, SCREEN_LOBBY)
    quick_menu = _runtime_snapshot(
        31,
        0,
        SCREEN_LOBBY,
        overlays=(MENU_QUICK,),
    )
    character_select = _runtime_snapshot(32, 0)
    actions = Actions()

    final = diagnostic._open_character_select(
        NavigationObserver(lobby, [quick_menu, character_select]),
        actions,
        timeout=6.0,
        settle_for=0.75,
    )

    assert final is character_select
    assert [type(call[0]).__name__ for call in actions.calls] == [
        "OpenQuickMenu",
        "OpenCharacterSelect",
    ]


def test_diagnostic_never_selects_a_character_or_calls_adb_directly():
    source = Path(diagnostic.__file__).read_text(encoding="utf-8")

    assert "SelectLastVisibleCharacter" not in source
    assert "ObservedScroll(" in source
    assert ".tap(" not in source
    assert ".swipe(" not in source
    assert ".shell(" not in source
