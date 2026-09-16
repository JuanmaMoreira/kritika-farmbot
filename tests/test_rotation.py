from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_CHARACTER_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
)
from bot.character_select_layout import COLUMN_CENTERS, predecessor_center
from bot.component_contracts import QUICK_MENU_ACCESS_REQUIREMENT
from bot.create_character_sentinel import CreateCharacterSentinelReading
from bot.observations import ObservationBatch
from bot.quick_menu import (
    DEFAULT_QUICK_MENU_POLICY,
    QuickMenuPolicy,
    open_character_select_action,
)
from bot.character_selection import DEFAULT_CHARACTER_SELECTION_DETECTOR
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
    QuickMenuLayout,
    SelectCharacterCard,
    Swipe,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]
COND01 = (
    "screencaps/semantic/character_select/sentinel/plus-col2-bottom.png"
)

SENTINEL_COL2 = (COLUMN_CENTERS[1], 0.75)
SENTINEL_COL1 = (COLUMN_CENTERS[0], 0.75)


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
        item_or_items = self.waits.pop(0)
        if isinstance(item_or_items, BaseException):
            raise item_or_items
        items = (
            item_or_items
            if isinstance(item_or_items, list)
            else [item_or_items]
        )
        matched = False
        for item in items:
            assert item.sequence > after_sequence
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            matched = condition(item)
        assert matched
        return items[-1]


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


class ScriptedSentinel:
    """Yield scripted sentinel readings, repeating the last one."""

    def __init__(self, readings):
        self.readings = list(readings)
        self.calls = 0

    def measure(self, frame):
        self.calls += 1
        if len(self.readings) > 1:
            return self.readings.pop(0)
        return self.readings[0]


def _found(location=SENTINEL_COL2, score=0.95):
    return CreateCharacterSentinelReading(True, score, location)


def _absent(score=0.10):
    return CreateCharacterSentinelReading(False, score, None)


def _frame(fill=0, *, grid_fill=None):
    image = np.full((200, 400, 3), fill, dtype=np.uint8)
    if grid_fill is not None:
        image[38:161, 196:340] = grid_fill
    return image


def _selected_frame_at(image, center):
    """Paint a full yellow ring exactly on the tile box of ``center``."""
    from bot.character_select_layout import tile_box
    from bot.geometry import relative_region_to_pixels

    selected = image.copy()
    height, width = selected.shape[:2]
    x1, y1, x2, y2 = relative_region_to_pixels(
        tile_box(center), width, height
    )
    crop = selected[y1:y2, x1:x2]
    border_x = round(
        crop.shape[1] * DEFAULT_CHARACTER_SELECTION_DETECTOR.border_x_fraction
    )
    border_y = round(
        crop.shape[0] * DEFAULT_CHARACTER_SELECTION_DETECTOR.border_y_fraction
    )
    crop[:, :border_x] = (0, 255, 255)
    crop[:, -border_x:] = (0, 255, 255)
    crop[:border_y, :] = (0, 255, 255)
    crop[-border_y:, :] = (0, 255, 255)
    return selected


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
    sentinel = kwargs.pop("sentinel", None)
    if sentinel is None and "sentinel_detector" not in kwargs:
        sentinel = ScriptedSentinel([_absent()])
    if sentinel is not None:
        kwargs["sentinel_detector"] = sentinel
    rotation = StandardRotation(
        observer,
        actions,
        events,
        **kwargs,
    )
    return rotation, actions, events, observer


def _expected_tap(location):
    return SelectCharacterCard(predecessor_center(location))


def test_standard_rotation_contract_and_character_count_configuration():
    rotation, _, _, _ = _rotation([], [], character_count=28)

    assert isinstance(rotation, RotationStrategy)
    assert rotation.character_count == 28
    assert rotation.max_swipes == 6
    assert rotation.contract.precondition == QUICK_MENU_ACCESS_REQUIREMENT


@pytest.mark.parametrize("max_swipes", (0, -1, 1.5, True))
def test_max_swipes_must_be_a_positive_integer(max_swipes):
    with pytest.raises(ValueError, match="max_swipes"):
        _rotation([], [], max_swipes=max_swipes)


@pytest.mark.parametrize("coarse_swipes", (-1, 1.5, True))
def test_coarse_swipes_must_be_a_non_negative_integer(coarse_swipes):
    with pytest.raises(ValueError, match="coarse_swipes"):
        _rotation([], [], coarse_swipes=coarse_swipes)


def test_sentinel_detector_must_provide_measure():
    with pytest.raises(ValueError, match="sentinel_detector"):
        _rotation([], [], sentinel_detector=object())


def test_rotation_opens_shifted_quick_menu_from_completed_guild():
    initial = _snapshot(
        1,
        base=SCREEN_GUILD,
        overlays={STATUS_GUILD_ATTENDANCE_COMPLETED},
    )
    rotation, actions, _, _ = _rotation(
        [initial],
        [
            _snapshot(2, base=SCREEN_GUILD, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(
                    _frame(grid_fill=80), predecessor_center(SENTINEL_COL2)
                ),
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert actions.actions[:2] == [
        OpenQuickMenu(),
        OpenCharacterSelect(QuickMenuLayout.SHIFTED),
    ]


def test_sentinel_visible_at_entry_selects_predecessor_without_swiping():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, events, observer = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    assert result.succeeded
    assert result.swipe_count == 0
    assert actions.actions == [
        OpenQuickMenu(),
        open_character_select_action(
            SCREEN_LOBBY, policy=DEFAULT_QUICK_MENU_POLICY
        ),
        _expected_tap(SENTINEL_COL2),
        ConfirmCharacterSelection(),
    ]
    assert events.events == []
    assert [trace.name for trace in result.transitions] == [
        "rotation.open_quick_menu",
        "rotation.open_character_select",
        "rotation.select_predecessor_character",
        "rotation.confirm_character_selection",
    ]
    assert all(
        trace.outcome == "success_first_attempt"
        and trace.attempt_count == 1
        and trace.grace_wait_count == 0
        for trace in result.transitions
    )
    assert result.transitions[2].effect_state == "selected"
    assert observer.wait_calls == [(1, 0.0), (2, 1.0), (3, 0.25), (4, 0.0)]


def test_sentinel_appearing_after_one_swipe_selects():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(
                5,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 1
    swipes = [action for action in actions.actions if isinstance(action, Swipe)]
    assert swipes == [CharacterSelectScrollProfile().progress_swipe]
    assert _expected_tap(SENTINEL_COL2) in actions.actions
    assert ConfirmCharacterSelection() in actions.actions


def test_sentinel_appearing_on_second_coarse_swipe_uses_no_fine():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _absent(), _found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 2
    profile = CharacterSelectScrollProfile()
    assert [a for a in actions.actions if isinstance(a, Swipe)] == [
        profile.progress_swipe,
        profile.progress_swipe,
    ]


def test_fine_swipe_reveals_partial_sentinel_after_two_coarse():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(
                7,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(8, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _absent(), _absent(), _found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 3
    profile = CharacterSelectScrollProfile()
    assert [a for a in actions.actions if isinstance(a, Swipe)] == [
        profile.progress_swipe,
        profile.progress_swipe,
        profile.fine_swipe,
    ]
    assert _expected_tap(SENTINEL_COL2) in actions.actions
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _absent(), _found()]),
        max_swipes=6,
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 2
    assert _expected_tap(SENTINEL_COL2) in actions.actions


def test_identical_frames_across_swipes_are_not_bottom_evidence():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _absent(), _found()]),
        max_swipes=6,
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 2
    assert _expected_tap(SENTINEL_COL2) in actions.actions


def test_sentinel_never_found_aborts_after_max_swipes():
    grid = _frame(grid_fill=80)
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
        ],
        sentinel=ScriptedSentinel([_absent()]),
        max_swipes=2,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error == "sentinel_not_found_after_max_swipes"
    assert result.swipe_count == 2
    assert sum(isinstance(action, Swipe) for action in actions.actions) == 2
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )
    assert ConfirmCharacterSelection() not in actions.actions
    assert events.events == ["rotation.standard.unexpected_state"]


def test_default_budget_allows_six_swipes():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(8, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(9, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
        ],
        sentinel=ScriptedSentinel([_absent()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error == "sentinel_not_found_after_max_swipes"
    assert result.swipe_count == 6
    profile = CharacterSelectScrollProfile()
    assert [a for a in actions.actions if isinstance(a, Swipe)] == [
        profile.progress_swipe,
        profile.progress_swipe,
        profile.fine_swipe,
        profile.fine_swipe,
        profile.fine_swipe,
        profile.fine_swipe,
    ]
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )


def test_unknown_frame_during_settle_is_tolerated_without_input():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, observer = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            [
                _snapshot(4, status=ResolutionStatus.UNKNOWN),
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            ],
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 1
    assert observer.wait_calls == [
        (1, 0.0),
        (2, 1.0),
        (3, 1.0),
        (5, 0.25),
        (6, 0.0),
    ]


def test_ambiguous_frame_during_settle_is_tolerated_without_input():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            [
                _snapshot(4, status=ResolutionStatus.AMBIGUOUS),
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            ],
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 1
    assert not any(
        isinstance(action, SelectCharacterCard)
        for action in actions.actions[:3]
    )


def test_settle_aborts_on_contradictory_after_transient_unknown():
    grid = _frame(grid_fill=80)
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            [
                _snapshot(4, status=ResolutionStatus.UNKNOWN),
                _snapshot(5, base=SCREEN_LOBBY),
            ],
        ],
        sentinel=ScriptedSentinel([_absent()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "unexpected_state" in result.error
    assert result.swipe_count == 1
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )
    assert events.events == ["rotation.standard.unexpected_state"]


def test_contradictory_context_after_swipe_aborts_without_selection():
    grid = _frame(grid_fill=80)
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "unexpected_state" in result.error
    assert result.swipe_count == 1
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )
    assert events.events == ["rotation.standard.unexpected_state"]


def test_settle_timeout_after_swipe_aborts():
    timeout = RuntimeWaitTimeout(
        after_sequence=3,
        timeout=6.0,
        last_snapshot=_snapshot(4, base=SCREEN_CHARACTER_SELECT),
    )
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT),
            timeout,
        ],
        sentinel=ScriptedSentinel([_absent()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("character_select_settle_failed")
    assert result.swipe_count == 1
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )


def test_invalid_sentinel_location_aborts_without_tap():
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT),
        ],
        sentinel=ScriptedSentinel([_found(location=(0.30, 0.75))]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("invalid_sentinel_location")
    assert result.swipe_count == 0
    assert not any(
        isinstance(action, SelectCharacterCard) for action in actions.actions
    )
    assert ConfirmCharacterSelection() not in actions.actions


def test_col1_sentinel_selects_col3_of_previous_row():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL1)
    assert target[0] == pytest.approx(COLUMN_CENTERS[2])
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found(location=SENTINEL_COL1)]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 0
    assert _expected_tap(SENTINEL_COL1) in actions.actions


def test_col3_sentinel_selects_col2_of_same_row():
    location = (COLUMN_CENTERS[2], 0.60)
    target = predecessor_center(location)
    assert target == (COLUMN_CENTERS[1], 0.60)
    grid = _frame(grid_fill=80)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found(location=location)]),
    )

    result = rotation.advance()

    assert result.succeeded
    assert SelectCharacterCard(target) in actions.actions


def test_preselected_target_still_authorizes_tap_and_succeeds():
    # Live evidence (game pre-selects the last-played character): the tap is
    # authorized by clean Character Select plus the confirmed sentinel, never
    # gated on the pre-tap selection state. Verification stays post-tap.
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    selected = _selected_frame_at(grid, target)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=selected),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid.copy(), target),
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert taps == [_expected_tap(SENTINEL_COL2)]
    assert ConfirmCharacterSelection() in actions.actions


def test_card_tap_without_effect_retries_only_from_fresh_unselected_state():
    edge_image = _frame(grid_fill=80)
    rotation, actions, _events, _observer = _rotation(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            _snapshot(10, base=SCREEN_CHARACTER_SELECT, image=edge_image),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=1.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=0.75,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=7,
                timeout=1.0,
                last_snapshot=_snapshot(
                    8, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=8,
                timeout=0.75,
                last_snapshot=_snapshot(
                    9, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "attempts_exhausted" in result.error
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert taps == [_expected_tap(SENTINEL_COL2)] * 2
    assert ConfirmCharacterSelection() not in actions.actions


def test_card_selection_appearing_during_grace_does_not_send_second_tap():
    edge_image = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=1.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            _snapshot(
                5,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(edge_image, target),
            ),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.succeeded
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert len(taps) == 1
    assert result.transitions[2].outcome == "success_after_grace"
    assert result.transitions[2].grace_wait_count == 1


def test_card_selection_leaving_character_select_aborts_without_retry():
    edge_image = _frame(grid_fill=80)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "unexpected_state" in result.error
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert len(taps) == 1
    assert ConfirmCharacterSelection() not in actions.actions


def test_selection_late_expected_proves_stability_entirely_on_scoped_transition():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    selected = _selected_frame_at(grid, target)
    main_observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )
    scoped_observer = ScriptedObserver(
        [_snapshot(6, base=SCREEN_CHARACTER_SELECT, image=selected)],
        [
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=1.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_CHARACTER_SELECT, image=selected
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=0.75,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=selected
                ),
            ),
            [
                _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=selected),
                _snapshot(8, base=SCREEN_CHARACTER_SELECT, image=selected),
            ],
        ],
    )
    actions = Actions()
    events = Events()
    rotation = StandardRotation(
        main_observer,
        actions,
        events,
        sentinel_detector=ScriptedSentinel([_found()]),
        verified_transition=VerifiedTransition(main_observer, actions, events),
        selection_transition=VerifiedTransition(
            scoped_observer, actions, events
        ),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.transitions[2].outcome == "success_after_grace"
    assert result.transitions[2].attempt_count == 1
    assert result.transitions[2].grace_wait_count == 1
    assert scoped_observer.wait_calls == [
        (3, 0.25),
        (4, 0.25),
        (6, 0.25),
    ]
    assert main_observer.wait_calls == [(1, 0.0), (2, 1.0), (8, 0.0)]
    assert actions.actions.count(SelectCharacterCard(target)) == 1
    assert actions.actions.count(ConfirmCharacterSelection()) == 1


def test_selection_retry_keeps_both_attempts_on_scoped_transition():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    selected = _selected_frame_at(grid, target)
    main_observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )
    scoped_observer = ScriptedObserver(
        [_snapshot(6, base=SCREEN_CHARACTER_SELECT, image=grid)],
        [
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=1.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=0.75,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            [
                _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=selected),
                _snapshot(8, base=SCREEN_CHARACTER_SELECT, image=selected),
            ],
        ],
    )
    actions = Actions()
    events = Events()
    rotation = StandardRotation(
        main_observer,
        actions,
        events,
        sentinel_detector=ScriptedSentinel([_found()]),
        verified_transition=VerifiedTransition(main_observer, actions, events),
        selection_transition=VerifiedTransition(
            scoped_observer, actions, events
        ),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.transitions[2].outcome == "success_after_retry"
    assert result.transitions[2].attempt_count == 2
    assert scoped_observer.wait_calls == [
        (3, 0.25),
        (4, 0.25),
        (6, 0.25),
    ]
    assert main_observer.wait_calls == [(1, 0.0), (2, 1.0), (8, 0.0)]
    assert actions.actions.count(SelectCharacterCard(target)) == 2
    assert actions.actions.count(ConfirmCharacterSelection()) == 1


def test_selection_target_comes_from_fresh_post_swipe_sentinel_snapshot():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    sentinel_location = (COLUMN_CENTERS[2], 0.60)
    target = predecessor_center(sentinel_location)
    selected = _selected_frame_at(grid, target)
    main_observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )
    scoped_observer = ScriptedObserver(
        [],
        [_snapshot(5, base=SCREEN_CHARACTER_SELECT, image=selected)],
    )
    actions = Actions()
    events = Events()
    rotation = StandardRotation(
        main_observer,
        actions,
        events,
        sentinel_detector=ScriptedSentinel(
            [_absent(), _found(location=sentinel_location)]
        ),
        scroll_profile=CharacterSelectScrollProfile(
            progress_swipe=Swipe((0.5, 0.7), (0.5, 0.3), 300),
            fine_swipe=Swipe((0.5, 0.7), (0.5, 0.5), 250),
            settle_for=0.25,
        ),
        verified_transition=VerifiedTransition(main_observer, actions, events),
        selection_transition=VerifiedTransition(
            scoped_observer, actions, events
        ),
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 1
    assert SelectCharacterCard(target) in actions.actions
    assert scoped_observer.wait_calls == [(4, 0.25)]
    assert main_observer.wait_calls[-1] == (5, 0.0)


@pytest.mark.parametrize(
    "unsafe",
    (
        _snapshot(6, status=ResolutionStatus.UNKNOWN),
        _snapshot(
            6,
            base=SCREEN_CHARACTER_SELECT,
            overlays={MENU_QUICK},
        ),
    ),
)
def test_selection_unknown_or_overlay_never_authorizes_extra_input(unsafe):
    grid = _frame(grid_fill=80)
    main_observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
        ],
    )
    if unsafe.state.overlays:
        waits = [unsafe]
        observes = []
    else:
        waits = [
            RuntimeWaitTimeout(
                after_sequence=3, timeout=1.0, last_snapshot=_snapshot(4)
            ),
            RuntimeWaitTimeout(
                after_sequence=4, timeout=0.75, last_snapshot=_snapshot(5)
            ),
        ]
        observes = [unsafe]
    scoped_observer = ScriptedObserver(observes, waits)
    actions = Actions()
    events = Events()
    rotation = StandardRotation(
        main_observer,
        actions,
        events,
        sentinel_detector=ScriptedSentinel([_found()]),
        verified_transition=VerifiedTransition(main_observer, actions, events),
        selection_transition=VerifiedTransition(
            scoped_observer, actions, events
        ),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert sum(isinstance(item, SelectCharacterCard) for item in actions.actions) == 1
    assert ConfirmCharacterSelection() not in actions.actions


def test_unknown_startup_frame_waits_for_fresh_capable_context_before_input():
    normal_timeout = RuntimeWaitTimeout(
        after_sequence=2,
        timeout=6.0,
        last_snapshot=_snapshot(3, base=SCREEN_LOBBY),
    )
    grace_timeout = RuntimeWaitTimeout(
        after_sequence=3,
        timeout=2.0,
        last_snapshot=_snapshot(4, base=SCREEN_LOBBY),
    )
    rotation, actions, events, observer = _rotation(
        [_snapshot(1), _snapshot(5, base="screen.other")],
        [
            _snapshot(2, base=SCREEN_LOBBY),
            normal_timeout,
            grace_timeout,
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("quick_menu_navigation_failed")
    assert "unexpected_state" in result.error
    assert actions.actions == [OpenQuickMenu()]
    assert observer.wait_calls == [(1, 0.25), (2, 0.0), (3, 0.0)]
    assert events.events == ["rotation.standard.unexpected_state"]


def test_resolved_context_without_quick_menu_capability_aborts_without_input():
    rotation, actions, events, observer = _rotation(
        [_snapshot(1, base=SCREEN_CHARACTER_SELECT)],
        [],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error == "precondition_quick_menu_accessible_failed"
    assert actions.actions == []
    assert observer.wait_calls == []
    assert events.events == ["rotation.standard.unexpected_state"]


def test_quick_menu_safe_retry_is_bounded_to_configured_attempts():
    rotation, actions, events, _ = _rotation(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(4, base=SCREEN_LOBBY),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        [
            RuntimeWaitTimeout(
                after_sequence=1,
                timeout=6.0,
                last_snapshot=_snapshot(2, base=SCREEN_LOBBY),
            ),
            RuntimeWaitTimeout(
                after_sequence=2,
                timeout=2.0,
                last_snapshot=_snapshot(3, base=SCREEN_LOBBY),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=6.0,
                last_snapshot=_snapshot(5, base=SCREEN_LOBBY),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(6, base=SCREEN_LOBBY),
            ),
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("quick_menu_navigation_failed")
    assert "attempts_exhausted" in result.error
    assert actions.actions == [OpenQuickMenu(), OpenQuickMenu()]
    assert result.transitions[0].attempt_count == 2
    assert events.events == ["rotation.standard.unexpected_state"]


def test_confirm_character_selection_retries_from_fresh_character_select():
    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    rotation, actions, events, _ = _rotation(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(9, base=SCREEN_CHARACTER_SELECT, image=grid),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(
                4,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame_at(grid, target),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=6.0,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(
                    6, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            _snapshot(10, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_found()]),
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    assert actions.actions[-2:] == [
        ConfirmCharacterSelection(),
        ConfirmCharacterSelection(),
    ]
    assert result.transitions[-1].outcome == "success_after_retry"
    assert result.transitions[-1].attempt_count == 2
    assert result.transitions[-1].grace_wait_count == 1
    assert events.events == []


def test_live_preselected_predecessor_succeeds_with_real_detectors():
    # sem_5400: live frame whose predecessor (col1 bottom row) carries the
    # yellow selection border. The old unselected-precondition aborted here
    # with precondition_rejected before any tap; the tap must be authorized
    # and post-tap verification must confirm the already-selected target.
    from bot.create_character_sentinel import DEFAULT_SENTINEL_DETECTOR

    image = cv2.imread(
        str(
            ROOT
            / "screencaps/semantic/character_select/20260823T025400_922432Z.png"
        )
    )
    assert image is not None
    observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=image),
            _snapshot(
                4, base=SCREEN_CHARACTER_SELECT, image=image.copy()
            ),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
    )
    actions = Actions()
    rotation = StandardRotation(
        observer,
        actions,
        Events(),
        sentinel_detector=DEFAULT_SENTINEL_DETECTOR,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    assert result.swipe_count == 0
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert len(taps) == 1
    assert taps[0].center[0] == pytest.approx(COLUMN_CENTERS[0])
    assert result.transitions[2].effect_state == "selected"
    assert result.transitions[2].effect_score >= 0.05


def test_live_frame_detector_drives_predecessor_tap():
    from bot.create_character_sentinel import DEFAULT_SENTINEL_DETECTOR

    image = cv2.imread(str(ROOT / COND01))
    assert image is not None
    observer = ScriptedObserver(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=image),
            _snapshot(9, base=SCREEN_CHARACTER_SELECT, image=image),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=image),
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=1.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_CHARACTER_SELECT, image=image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=0.75,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=6,
                timeout=1.0,
                last_snapshot=_snapshot(
                    7, base=SCREEN_CHARACTER_SELECT, image=image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=7,
                timeout=0.75,
                last_snapshot=_snapshot(
                    8, base=SCREEN_CHARACTER_SELECT, image=image
                ),
            ),
        ],
    )
    actions = Actions()
    rotation = StandardRotation(
        observer,
        actions,
        Events(),
        sentinel_detector=DEFAULT_SENTINEL_DETECTOR,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("predecessor_selection_failed")
    assert result.swipe_count == 0
    taps = [
        action
        for action in actions.actions
        if isinstance(action, SelectCharacterCard)
    ]
    assert len(taps) == 2
    assert taps[0].center == predecessor_center((0.6675884955752213, 0.7483660130718954))
    assert taps[0].center[0] == pytest.approx(COLUMN_CENTERS[0])


def test_rotation_module_never_imports_or_calls_adb_directly():
    source = Path("bot/rotation.py").read_text(encoding="utf-8")

    assert "from bot.adb" not in source
    assert "import bot.adb" not in source
    assert ".tap(" not in source
    assert "self.adb" not in source


def test_rotation_no_longer_consumes_observed_scroll():
    source = Path("bot/rotation.py").read_text(encoding="utf-8")

    assert "ObservedScroll" not in source
    assert "observed_scroll" not in source
    assert "SelectLastVisibleCharacter" not in source
    assert "scroll_limit_reached" not in source


def test_post_swipe_wait_uses_scoped_observer_and_fresh_sentinel_frame():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    post = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy())
    scoped = ScriptedObserver([], [post])

    class RecordingSentinel(ScriptedSentinel):
        def __init__(self):
            super().__init__([_absent(), _found()])
            self.frames = []

        def measure(self, frame):
            self.frames.append(frame)
            return super().measure(frame)

    sentinel = RecordingSentinel()
    rotation, actions, _, main = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=_selected_frame_at(grid, target)),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
        sentinel=sentinel,
        post_swipe_observer=scoped,
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 1
    assert scoped.wait_calls == [(3, 1.0)]
    assert main.wait_calls == [(1, 0.0), (2, 1.0), (4, 0.25), (5, 0.0)]
    assert sentinel.frames[1] is post.frame
    assert [a for a in actions.actions if isinstance(a, Swipe)] == [
        CharacterSelectScrollProfile().progress_swipe
    ]
    assert actions.actions.count(_expected_tap(SENTINEL_COL2)) == 1
    assert actions.actions.count(ConfirmCharacterSelection()) == 1


def test_every_coarse_and_fine_swipe_wait_uses_scoped_observer():
    from bot.character_select_scroll import CharacterSelectScrollProfile

    grid = _frame(grid_fill=80)
    target = predecessor_center(SENTINEL_COL2)
    scoped = ScriptedObserver([], [
        _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
        _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
        _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
    ])
    rotation, actions, _, main = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=_selected_frame_at(grid, target)),
            _snapshot(8, base=SCREEN_LOBBY),
        ],
        sentinel=ScriptedSentinel([_absent(), _absent(), _absent(), _found()]),
        post_swipe_observer=scoped,
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 3
    assert scoped.wait_calls == [(3, 1.0), (4, 1.0), (5, 1.0)]
    assert main.wait_calls == [(1, 0.0), (2, 1.0), (6, 0.25), (7, 0.0)]
    profile = CharacterSelectScrollProfile()
    assert [a for a in actions.actions if isinstance(a, Swipe)] == [
        profile.progress_swipe, profile.progress_swipe, profile.fine_swipe,
    ]
    assert actions.actions.count(_expected_tap(SENTINEL_COL2)) == 1
    assert actions.actions.count(ConfirmCharacterSelection()) == 1

def test_discovered_unknown_quick_menu_cannot_start_rotation_tile_input():
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, overlays={MENU_QUICK})], [],
    )
    result = rotation.advance()
    assert result.outcome is RotationOutcome.ABORTED
    assert actions.actions == []


def test_foreign_resolved_menu_after_verified_lobby_aborts_before_tile_input():
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [_snapshot(2, base=SCREEN_GUILD, overlays={MENU_QUICK})],
    )
    result = rotation.advance()
    assert result.outcome is RotationOutcome.ABORTED
    assert actions.actions == [OpenQuickMenu()]
    assert "unexpected_state" in result.error
