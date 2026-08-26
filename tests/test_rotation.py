from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import MENU_QUICK, SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from bot.character_select_scroll import CharacterSelectScrollDetector
from bot.observations import ObservationBatch
from bot.rotation import (
    RotationOutcome,
    RotationStrategy,
    StandardRotation,
)
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    ConfirmCharacterSelection,
    OpenCharacterSelect,
    OpenQuickMenu,
    ScrollCharacterSelectTowardEnd,
    SelectLastVisibleCharacter,
)
from bot.state import ResolutionStatus, ResolvedState


class ScriptedObserver:
    def __init__(self, observes, waits):
        self.observes = list(observes)
        self.waits = list(waits)
        self.wait_calls = []

    def observe(self):
        return self.observes.pop(0)

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        self.wait_calls.append((after_sequence, stable_for))
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item


class Actions:
    def __init__(self):
        self.actions = []

    def execute(self, action, geometry):
        self.actions.append(action)


class Events:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)


def _frame(fill=0, *, grid_fill=None):
    image = np.full((200, 400, 3), fill, dtype=np.uint8)
    if grid_fill is not None:
        image[38:161, 196:340] = grid_fill
    return image


def _snapshot(
    sequence,
    *,
    base=None,
    overlays=(),
    status=None,
    image=None,
):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    if image is None:
        image = _frame()
    timestamp = float(sequence)
    frame = FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence)
    batch = ObservationBatch(sequence=sequence, timestamp=timestamp)
    state = ResolvedState(
        status=status,
        sequence=sequence,
        timestamp=timestamp,
        base_context=base,
        overlays=tuple(overlays),
        base_candidates=(
            (SCREEN_LOBBY, SCREEN_CHARACTER_SELECT)
            if status is ResolutionStatus.AMBIGUOUS
            else ()
        ),
    )
    return RuntimeSnapshot(
        frame=frame,
        observations=batch,
        state=state,
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


def _rotation(observes, waits, **kwargs):
    observer = ScriptedObserver(observes, waits)
    actions = Actions()
    events = Events()
    rotation = StandardRotation(
        observer,
        actions,
        events,
        scroll_detector=CharacterSelectScrollDetector(
            unchanged_threshold=0.03
        ),
        **kwargs,
    )
    return rotation, actions, events, observer


def test_standard_rotation_contract_and_character_count_configuration():
    rotation, _, _, _ = _rotation([], [], character_count=28)

    assert isinstance(rotation, RotationStrategy)
    assert rotation.character_count == 28


@pytest.mark.parametrize("character_count", (0, -1, 1.5, True))
def test_character_count_must_be_a_positive_integer(character_count):
    with pytest.raises(ValueError, match="character_count"):
        _rotation([], [], character_count=character_count)


def test_advance_accepts_unknown_plus_quick_menu_and_changes_once():
    first_grid = _frame(grid_fill=40)
    scrolled_grid = _frame(grid_fill=230)
    rotation, actions, events, observer = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=first_grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=scrolled_grid),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=scrolled_grid.copy()),
            _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=scrolled_grid.copy()),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    assert result.succeeded
    assert result.swipe_count == 2
    assert result.end_difference == 0.0
    assert actions.actions == [
        OpenQuickMenu(),
        OpenCharacterSelect(),
        ScrollCharacterSelectTowardEnd(),
        ScrollCharacterSelectTowardEnd(),
        SelectLastVisibleCharacter(),
        ConfirmCharacterSelection(),
    ]
    assert events.events == []
    assert observer.wait_calls == [
        (1, 0.0),
        (2, 0.0),
        (3, 0.6),
        (4, 0.6),
        (5, 0.25),
        (6, 0.0),
    ]


def test_scroll_limit_aborts_before_character_selection():
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=_frame(grid_fill=10)),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=_frame(grid_fill=100)),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=_frame(grid_fill=220)),
        ],
        max_swipes=2,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error == "scroll_limit_reached"
    assert result.swipe_count == 2
    assert actions.actions[-1] == ScrollCharacterSelectTowardEnd()
    assert SelectLastVisibleCharacter() not in actions.actions
    assert ConfirmCharacterSelection() not in actions.actions
    assert events.events == ["rotation.standard.unexpected_state"]


def test_quick_menu_timeout_aborts_without_more_input():
    timeout = RuntimeWaitTimeout(
        after_sequence=1,
        timeout=6.0,
        last_snapshot=_snapshot(2, base=SCREEN_LOBBY),
    )
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)], [timeout]
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("quick_menu_navigation_failed")
    assert actions.actions == [OpenQuickMenu()]
    assert events.events == ["rotation.standard.unexpected_state"]


def test_fresh_lobby_is_required_after_confirming_selection():
    grid = _frame(grid_fill=80)
    timeout = RuntimeWaitTimeout(
        after_sequence=5,
        timeout=6.0,
        last_snapshot=_snapshot(6, base=SCREEN_CHARACTER_SELECT, image=grid),
    )
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            timeout,
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("return_to_lobby_failed")
    assert actions.actions[-1] == ConfirmCharacterSelection()
    assert events.events == ["rotation.standard.unexpected_state"]


def test_rotation_module_never_imports_or_calls_adb_directly():
    source = Path("bot/rotation.py").read_text(encoding="utf-8")

    assert "from bot.adb" not in source
    assert "import bot.adb" not in source
    assert ".tap(" not in source
    assert "self.adb" not in source
