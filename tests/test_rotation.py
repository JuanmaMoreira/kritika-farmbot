from pathlib import Path
from concurrent.futures import Future

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import MENU_QUICK, SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from bot.character_select_scroll import CharacterSelectScrollProfile
from bot.observed_scroll import (
    ObservedScroll,
    ObservedScrollOutcome,
    ObservedScrollResult,
    ScrollAttemptKind,
    ScrollAttemptMeasurement,
)
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
    SelectLastVisibleCharacter,
    Swipe,
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


class InlineExecutor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as error:
            future.set_exception(error)
        return future


class TrackingExecutor(InlineExecutor):
    def __init__(self):
        self.exited = False

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        return False


class DelegatingScroll:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def scroll_to_edge(self, before, **kwargs):
        self.calls.append((before, kwargs))
        return self.result


def _frame(fill=0, *, grid_fill=None):
    image = np.full((200, 400, 3), fill, dtype=np.uint8)
    if grid_fill is not None:
        image[38:161, 196:340] = grid_fill
    return image


def _selected_frame(image):
    selected = image.copy()
    height, width = selected.shape[:2]
    x1, x2 = round(width * 0.48), round(width * 0.63)
    y1, y2 = round(height * 0.64), round(height * 0.84)
    crop = selected[y1:y2, x1:x2]
    border_x = round(crop.shape[1] * 0.16)
    border_y = round(crop.shape[0] * 0.18)
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
    swipe_executor_factory = kwargs.pop(
        "swipe_executor_factory", InlineExecutor
    )
    profile_kwargs = {}
    for old_name, profile_name in (
        ("max_swipes", "max_attempts"),
        ("end_confirmation_swipes", "required_confirmations"),
        ("movement_threshold", "movement_threshold"),
        ("scroll_settle_for", "settle_for"),
    ):
        if old_name in kwargs:
            profile_kwargs[profile_name] = kwargs.pop(old_name)
    scroll_profile = CharacterSelectScrollProfile(**profile_kwargs)
    observed_scroll = ObservedScroll(
        observer,
        actions,
        swipe_executor_factory=swipe_executor_factory,
    )
    rotation = StandardRotation(
        observer,
        actions,
        events,
        scroll_profile=scroll_profile,
        observed_scroll=observed_scroll,
        **kwargs,
    )
    return rotation, actions, events, observer


def test_standard_rotation_contract_and_character_count_configuration():
    rotation, _, _, _ = _rotation([], [], character_count=28)

    assert isinstance(rotation, RotationStrategy)
    assert rotation.character_count == 28


def test_rotation_delegates_scroll_algorithm_to_observed_scroll():
    initial = _snapshot(1, base=SCREEN_LOBBY)
    character_select = _snapshot(3, base=SCREEN_CHARACTER_SELECT)
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT)
    measurement = ScrollAttemptMeasurement(
        pre_sequence=3,
        settled_sequence=4,
        fresh_sample_count=2,
        transient_peak_sequence=4,
        max_transient_difference=0.14,
        settled_difference=0.02,
    )
    delegated = DelegatingScroll(
        ObservedScrollResult(
            outcome=ObservedScrollOutcome.EDGE_REACHED,
            final_snapshot=edge,
            attempts=(measurement,),
            attempt_kinds=(ScrollAttemptKind.EDGE_CANDIDATE,),
            effective_gesture_count=1,
            confirmation_count=1,
        )
    )
    observer = ScriptedObserver(
        [initial],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            character_select,
            _snapshot(
                5,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(edge.frame.image),
            ),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )
    actions = Actions()
    rotation = StandardRotation(
        observer,
        actions,
        Events(),
        observed_scroll=delegated,
    )

    result = rotation.advance()

    assert result.succeeded
    assert len(delegated.calls) == 1
    before, arguments = delegated.calls[0]
    assert before is character_select
    assert arguments["config"] == rotation.scroll_profile.config()
    assert arguments["detector"] == rotation.scroll_profile.detector()
    assert SelectLastVisibleCharacter() in actions.actions


@pytest.mark.parametrize("character_count", (0, -1, 1.5, True))
def test_character_count_must_be_a_positive_integer(character_count):
    with pytest.raises(ValueError, match="character_count"):
        _rotation([], [], character_count=character_count)


@pytest.mark.parametrize("end_confirmation_swipes", (0, -1, 1.5, True))
def test_end_confirmation_swipes_must_be_a_positive_integer(
    end_confirmation_swipes,
):
    with pytest.raises(ValueError, match="required_confirmations"):
        _rotation(
            [], [], end_confirmation_swipes=end_confirmation_swipes
        )


def test_end_confirmation_swipes_must_fit_inside_swipe_limit():
    with pytest.raises(ValueError, match="must not exceed max_attempts"):
        _rotation([], [], max_swipes=1, end_confirmation_swipes=2)


@pytest.mark.parametrize("movement_threshold", (-0.1, 1.1, True))
def test_movement_threshold_must_be_normalized(movement_threshold):
    with pytest.raises(ValueError, match="movement_threshold"):
        _rotation([], [], movement_threshold=movement_threshold)


def test_advance_accepts_unknown_plus_quick_menu_and_changes_once():
    first_grid = _frame(grid_fill=40)
    scrolled_grid = _frame(grid_fill=230)
    rotation, actions, events, observer = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=first_grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=scrolled_grid),
            [
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=first_grid),
                _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=scrolled_grid.copy()),
            ],
            _snapshot(
                7,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(scrolled_grid),
            ),
            _snapshot(8, base=SCREEN_LOBBY),
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.SUCCESS
    assert result.succeeded
    assert result.swipe_count == 2
    assert result.effective_swipe_count == 2
    assert result.bottom_confirmation_count == 1
    assert result.end_difference == 0.0
    assert result.scroll_attempt_kinds == (
        ScrollAttemptKind.PROGRESS,
        ScrollAttemptKind.EDGE_CANDIDATE,
    )
    assert actions.actions == [
        OpenQuickMenu(),
        OpenCharacterSelect(),
        CharacterSelectScrollProfile().progress_swipe,
        CharacterSelectScrollProfile().confirmation_swipe,
        SelectLastVisibleCharacter(),
        ConfirmCharacterSelection(),
    ]
    assert events.events == []
    assert [trace.name for trace in result.transitions] == [
        "rotation.open_quick_menu",
        "rotation.open_character_select",
        "rotation.select_last_visible_character",
        "rotation.confirm_character_selection",
    ]
    assert all(
        trace.outcome == "success_first_attempt"
        and trace.attempt_count == 1
        and trace.grace_wait_count == 0
        for trace in result.transitions
    )
    assert observer.wait_calls == [
        (1, 0.0),
        (2, 1.0),
        (3, 1.0),
        (4, 1.0),
        (6, 0.25),
        (7, 0.0),
    ]


def test_unknown_startup_frame_waits_for_fresh_lobby_before_input():
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
    assert "retry_guard_rejected" in result.error
    assert actions.actions == [OpenQuickMenu()]
    assert observer.wait_calls == [(1, 0.25), (2, 0.0), (3, 0.0)]
    assert events.events == ["rotation.standard.unexpected_state"]


def test_resolved_non_lobby_precondition_aborts_without_wait_or_input():
    rotation, actions, events, observer = _rotation(
        [_snapshot(1, base=SCREEN_CHARACTER_SELECT)],
        [],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error == "precondition_lobby_failed"
    assert actions.actions == []
    assert observer.wait_calls == []
    assert events.events == ["rotation.standard.unexpected_state"]


def test_ineffective_swipe_aborts_without_selecting_or_spending_third_attempt():
    initial_grid = _frame(grid_fill=40)
    moved_grid = _frame(grid_fill=220)
    rotation, actions, events, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=initial_grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=initial_grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=moved_grid),
            [
                _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=initial_grid),
                _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=moved_grid.copy()),
            ],
            _snapshot(8, base=SCREEN_CHARACTER_SELECT, image=moved_grid.copy()),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.endswith("ineffective_gesture")
    assert result.swipe_count == 1
    assert result.effective_swipe_count == 0
    assert result.scroll_attempt_kinds[0] is ScrollAttemptKind.INEFFECTIVE
    assert sum(isinstance(action, Swipe) for action in actions.actions) == 1
    assert SelectLastVisibleCharacter() not in actions.actions
    assert ConfirmCharacterSelection() not in actions.actions
    assert events.events == ["rotation.standard.unexpected_state"]


def test_zero_effective_swipes_never_confirms_bottom_or_selects():
    grid = _frame(grid_fill=80)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
        ],
        max_swipes=2,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.endswith("ineffective_gesture")
    assert result.effective_swipe_count == 0
    assert result.bottom_confirmation_count == 0
    assert result.scroll_attempt_kinds == (ScrollAttemptKind.INEFFECTIVE,)
    assert SelectLastVisibleCharacter() not in actions.actions


def test_configured_double_confirmation_does_not_accept_one_bounce():
    first_grid = _frame(grid_fill=40)
    bottom_grid = _frame(grid_fill=220)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=first_grid),
            _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=bottom_grid),
            [
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=first_grid),
                _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=bottom_grid.copy()),
            ],
        ],
        max_swipes=2,
        end_confirmation_swipes=2,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.bottom_confirmation_count == 1
    assert result.scroll_attempt_kinds[-1] is ScrollAttemptKind.EDGE_CANDIDATE
    assert SelectLastVisibleCharacter() not in actions.actions


def test_configured_double_confirmation_selects_after_two_effective_bounces():
    grid = _frame(grid_fill=80)
    transient = _frame(grid_fill=220)
    rotation, actions, _, _ = _rotation(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            [
                _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=transient),
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            ],
            [
                _snapshot(6, base=SCREEN_CHARACTER_SELECT, image=transient),
                _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            ],
            _snapshot(
                8,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(grid),
            ),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
        end_confirmation_swipes=2,
    )

    result = rotation.advance()

    assert result.succeeded
    assert result.swipe_count == 2
    assert result.effective_swipe_count == 2
    assert result.bottom_confirmation_count == 2
    assert result.scroll_attempt_kinds == (
        ScrollAttemptKind.EDGE_CANDIDATE,
        ScrollAttemptKind.EDGE_CANDIDATE,
    )
    assert SelectLastVisibleCharacter() in actions.actions


def test_scroll_timeout_exits_swipe_executor_and_never_selects():
    tracker = TrackingExecutor()
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
        swipe_executor_factory=lambda: tracker,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert result.error.startswith("character_select_scroll_failed")
    assert tracker.exited
    assert SelectLastVisibleCharacter() not in actions.actions


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
    assert isinstance(actions.actions[-1], Swipe)
    assert SelectLastVisibleCharacter() not in actions.actions
    assert ConfirmCharacterSelection() not in actions.actions
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
    rotation, actions, events, _ = _rotation(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(9, base=SCREEN_CHARACTER_SELECT, image=grid),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=grid),
            [
                _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=_frame(grid_fill=200)),
                _snapshot(5, base=SCREEN_CHARACTER_SELECT, image=grid.copy()),
            ],
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(grid),
            ),
            RuntimeWaitTimeout(
                after_sequence=6,
                timeout=6.0,
                last_snapshot=_snapshot(
                    7, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=7,
                timeout=2.0,
                last_snapshot=_snapshot(
                    8, base=SCREEN_CHARACTER_SELECT, image=grid
                ),
            ),
            _snapshot(10, base=SCREEN_LOBBY),
        ],
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


def _edge_result(snapshot):
    measurement = ScrollAttemptMeasurement(
        pre_sequence=snapshot.sequence - 1,
        settled_sequence=snapshot.sequence,
        fresh_sample_count=2,
        transient_peak_sequence=snapshot.sequence,
        max_transient_difference=0.14,
        settled_difference=0.02,
    )
    return ObservedScrollResult(
        outcome=ObservedScrollOutcome.EDGE_REACHED,
        final_snapshot=snapshot,
        attempts=(measurement,),
        attempt_kinds=(ScrollAttemptKind.EDGE_CANDIDATE,),
        effective_gesture_count=1,
        confirmation_count=1,
    )


def _rotation_with_delegated_edge(observes, waits, edge):
    observer = ScriptedObserver(observes, waits)
    actions = Actions()
    rotation = StandardRotation(
        observer,
        actions,
        Events(),
        observed_scroll=DelegatingScroll(_edge_result(edge)),
    )
    return rotation, actions, observer


def test_card_selection_appearing_during_grace_does_not_send_second_tap():
    edge_image = _frame(grid_fill=80)
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=edge_image)
    rotation, actions, _ = _rotation_with_delegated_edge(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=1.0,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            _snapshot(
                6,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(edge_image),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
        edge,
    )

    result = rotation.advance()

    assert result.succeeded
    assert actions.actions.count(SelectLastVisibleCharacter()) == 1
    assert result.transitions[2].outcome == "success_after_grace"
    assert result.transitions[2].grace_wait_count == 1


def test_card_tap_without_effect_retries_only_from_fresh_unselected_state():
    edge_image = _frame(grid_fill=80)
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=edge_image)
    rotation, actions, _ = _rotation_with_delegated_edge(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=edge_image),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=1.0,
                last_snapshot=_snapshot(
                    5, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=0.75,
                last_snapshot=_snapshot(
                    6, base=SCREEN_CHARACTER_SELECT, image=edge_image
                ),
            ),
            _snapshot(
                8,
                base=SCREEN_CHARACTER_SELECT,
                image=_selected_frame(edge_image),
            ),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
        edge,
    )

    result = rotation.advance()

    assert result.succeeded
    assert actions.actions.count(SelectLastVisibleCharacter()) == 2
    assert result.transitions[2].outcome == "success_after_retry"
    assert result.transitions[2].attempt_count == 2
    assert result.transitions[2].effect_state == "selected"


def test_card_selection_attempts_exhaust_without_executing_select():
    edge_image = _frame(grid_fill=80)
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=edge_image)
    rotation, actions, _ = _rotation_with_delegated_edge(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(7, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            _snapshot(10, base=SCREEN_CHARACTER_SELECT, image=edge_image),
        ],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=1.0,
                last_snapshot=_snapshot(5, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=0.75,
                last_snapshot=_snapshot(6, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            ),
            RuntimeWaitTimeout(
                after_sequence=7,
                timeout=1.0,
                last_snapshot=_snapshot(8, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            ),
            RuntimeWaitTimeout(
                after_sequence=8,
                timeout=0.75,
                last_snapshot=_snapshot(9, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            ),
        ],
        edge,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "attempts_exhausted" in result.error
    assert actions.actions.count(SelectLastVisibleCharacter()) == 2
    assert ConfirmCharacterSelection() not in actions.actions


def test_card_selection_leaving_character_select_aborts_without_retry_or_select():
    edge_image = _frame(grid_fill=80)
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=edge_image)
    rotation, actions, _ = _rotation_with_delegated_edge(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=edge_image),
            _snapshot(5, base=SCREEN_LOBBY),
        ],
        edge,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "unexpected_state" in result.error
    assert actions.actions.count(SelectLastVisibleCharacter()) == 1
    assert ConfirmCharacterSelection() not in actions.actions


def test_preexisting_selected_frame_is_not_attributed_to_a_new_tap():
    edge_image = _selected_frame(_frame(grid_fill=80))
    edge = _snapshot(4, base=SCREEN_CHARACTER_SELECT, image=edge_image)
    rotation, actions, _ = _rotation_with_delegated_edge(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, overlays={MENU_QUICK}),
            _snapshot(3, base=SCREEN_CHARACTER_SELECT, image=_frame(grid_fill=80)),
        ],
        edge,
    )

    result = rotation.advance()

    assert result.outcome is RotationOutcome.ABORTED
    assert "precondition_rejected" in result.error
    assert SelectLastVisibleCharacter() not in actions.actions
    assert ConfirmCharacterSelection() not in actions.actions


def test_rotation_module_never_imports_or_calls_adb_directly():
    source = Path("bot/rotation.py").read_text(encoding="utf-8")

    assert "from bot.adb" not in source
    assert "import bot.adb" not in source
    assert ".tap(" not in source
    assert "self.adb" not in source
