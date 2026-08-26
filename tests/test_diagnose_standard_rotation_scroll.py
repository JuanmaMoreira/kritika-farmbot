from concurrent.futures import Future
from pathlib import Path

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_CHARACTER_SELECT
from bot.character_select_scroll import CharacterSelectScrollDetector
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
import tools.diagnose_standard_rotation_scroll as diagnostic


def _runtime_snapshot(sequence, fill):
    image = np.full((200, 400, 3), fill, dtype=np.uint8)
    timestamp = float(sequence)
    frame = FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence)
    return RuntimeSnapshot(
        frame=frame,
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=ResolutionStatus.RESOLVED,
            sequence=sequence,
            timestamp=timestamp,
            base_context=SCREEN_CHARACTER_SELECT,
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


class CompletedExecutor:
    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as error:
            future.set_exception(error)
        return future


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


def test_measurement_uses_only_fresh_post_action_snapshots():
    before = _runtime_snapshot(4, 0)
    transient = _runtime_snapshot(5, 255)
    settled = _runtime_snapshot(6, 0)
    actions = Actions()

    final, measurement = diagnostic.measure_scroll_attempt(
        Observer([transient, settled]),
        actions,
        CharacterSelectScrollDetector(),
        before,
        CompletedExecutor(),
        timeout=6.0,
        settle_for=0.75,
    )

    assert final is settled
    assert measurement.pre_sequence == 4
    assert measurement.settled_sequence == 6
    assert measurement.transient_peak_sequence == 5
    assert measurement.max_transient_difference > 0
    assert measurement.settled_difference == 0
    assert len(actions.calls) == 1


def test_static_control_measures_fresh_frames_without_sending_input():
    before = _runtime_snapshot(10, 0)
    intermediate = _runtime_snapshot(11, 2)
    settled = _runtime_snapshot(12, 1)

    final, measurement = diagnostic.measure_static_control(
        Observer([intermediate, settled]),
        CharacterSelectScrollDetector(),
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
    assert args.attempts == 8
    assert args.end_confirmations == 1
    assert args.movement_threshold == 0.05
    assert (args.scroll_x, args.scroll_start_y, args.scroll_end_y) == (
        0.68,
        0.76,
        0.24,
    )
    assert args.scroll_duration_ms == 200


def test_diagnostic_requires_explicit_execute_acknowledgement(capsys):
    assert diagnostic.main([]) == 2
    assert "Refusing to send Android input" in capsys.readouterr().err


def test_diagnostic_never_selects_a_character_or_calls_adb_directly():
    source = Path(diagnostic.__file__).read_text(encoding="utf-8")

    assert "SelectLastVisibleCharacter" not in source
    assert "ConfirmCharacterSelection" not in source
    assert ".tap(" not in source
    assert ".swipe(" not in source
    assert ".shell(" not in source
