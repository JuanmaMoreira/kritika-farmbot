"""Daily tab-loop semantics at loop level.

Covers ``DailyQuestsFlow._wait_for_daily_tab``, the point the deferred front
left open: a small scope loses blockers and can turn an incompatible state
into an apparently valid/actionable one, so the loop stays on the global
observer. These tests pin the loop-level contract:

- a decision snapshot is produced only with positive CONTENT_READY
  (chrome + Daily active + rows populated + NOT loading);
- tab-active and content-readiness stay separate predicates;
- loading never authorizes a noop/input decision;
- relevant blockers abort instead of degrading to success;
- UNKNOWN/AMBIGUOUS never authorize input or retry;
- foreign RESOLVED aborts;
- Progress Reward keeps its own separate settle contract.

Predicate-level ready/loading matrices live in
``test_daily_readiness_perception.py``; UNKNOWN-tap isolation, stale-frame
rejection and retry bounds live in ``test_daily_quests_flow.py`` and are
referenced, not repeated here.
"""

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_DAILY_QUESTS_LOADING,
    INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
    MENU_QUICK,
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
)
from bot.daily_quests_flow import DailyQuestsFlow
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
)
from bot.semantic_actions import SelectDailyQuests
from bot.state import ResolutionStatus, ResolvedState


def _rows():
    return (
        Observation(
            INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
            0.95,
            ObservationSource.LOCAL_CV,
        ),
    )


def _loading():
    return (
        Observation(
            ACTIVITY_DAILY_QUESTS_LOADING, 0.95, ObservationSource.LOCAL_CV
        ),
    )


def _snapshot(sequence, timestamp, *, base, overlays=(), status=None,
              observations=(), base_candidates=()):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, tuple(observations)),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(base_candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


class _TabObserver:
    """Minimal observer seam for the tab-loop: fresh frames on demand."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.observe_calls = 0

    def observe(self):
        self.observe_calls += 1
        return self._frames.pop(0)

    def wait_until(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("tab-loop must not use wait_until")


class _Actions:
    def __init__(self):
        self.items = []

    def execute(self, action, geometry):
        self.items.append(action)


class _Events:
    def record(self, event, **fields):
        pass


def _loop(frames, initial, *, timeout=6.0):
    observer = _TabObserver(frames)
    actions = _Actions()
    now = [0.0]
    flow = DailyQuestsFlow(
        observer,
        actions,
        _Events(),
        navigation_timeout=timeout,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    return flow, observer, actions, now


def _clean_quests(sequence=10, timestamp=10.0):
    return _snapshot(sequence, timestamp, base=SCREEN_QUESTS)


def _ready_daily(sequence, timestamp, *, claimable=False, progress=False):
    overlays = [MODE_DAILY_QUESTS]
    if claimable:
        overlays.append(STATUS_DAILY_QUESTS_CLAIMABLE)
    if progress:
        overlays.append(STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE)
    return _snapshot(
        sequence, timestamp, base=SCREEN_QUESTS, overlays=overlays,
        observations=_rows(),
    )


# --- Tabs: active vs switching vs loading -------------------------------

def test_already_active_ready_returns_without_input():
    initial = _ready_daily(10, 10.0)
    flow, observer, actions, _ = _loop([], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is initial
    assert actions.items == []
    assert observer.observe_calls == 0


def test_other_tab_taps_once_then_continues_on_ready():
    initial = _clean_quests()
    ready = _ready_daily(11, 11.0)
    flow, _, actions, _ = _loop([ready], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is ready
    assert actions.items == [SelectDailyQuests()]


def test_daily_visible_but_loading_waits_for_ready():
    """Post-tap loading frame must not become the claim/noop decision."""
    initial = _clean_quests()
    loading_daily = _snapshot(
        11, 11.0, base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
        observations=(*_rows(), *_loading()),
    )
    assert not DailyQuestsFlow._is_content_ready(loading_daily)
    ready = _ready_daily(12, 12.0, claimable=True)
    flow, _, actions, _ = _loop([loading_daily, ready], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is ready
    assert STATUS_DAILY_QUESTS_CLAIMABLE in result.state.overlays
    assert actions.items == [SelectDailyQuests()]


# --- Claimable / noop gating ---------------------------------------------

def test_ready_without_claimable_is_the_only_legitimate_noop_basis():
    initial = _ready_daily(10, 10.0)
    assert DailyQuestsFlow._is_content_ready(initial)
    flow, _, actions, _ = _loop([], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is initial
    assert STATUS_DAILY_QUESTS_CLAIMABLE not in result.state.overlays
    assert actions.items == []


def test_chrome_without_claimable_and_without_readiness_never_decides():
    """Daily chrome + no claimable observed, but rows absent: the loop must
    keep waiting, never hand that frame to the claim/noop decision."""
    initial = _snapshot(
        10, 10.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
    )
    assert STATUS_DAILY_QUESTS_CLAIMABLE not in initial.state.overlays
    assert not DailyQuestsFlow._is_content_ready(initial)
    ready = _ready_daily(11, 11.0)
    flow, _, actions, _ = _loop([ready], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is ready
    assert result.sequence == 11
    assert actions.items == []


# --- Blockers: the defer cause --------------------------------------------

def test_blocker_overlay_withholds_actionable_while_scope_view_would_pass():
    """Counterexample for a detector subset that omits the blocker.

    Global perception resolves the blocker overlay, so the frame is neither
    Quests-clean nor content-ready. The same frame seen through a scope
    without that detector resolves as clean Daily + rows: false actionable.
    """
    blocked = _snapshot(
        11, 11.0, base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, MENU_QUICK),
        observations=_rows(),
    )
    assert not DailyQuestsFlow._is_quests(blocked)
    assert not DailyQuestsFlow._is_content_ready(blocked)

    scope_view = _snapshot(
        11, 11.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
        observations=_rows(),
    )
    assert DailyQuestsFlow._is_content_ready(scope_view)


def test_loop_aborts_on_blocker_frame_without_tapping_it():
    initial = _clean_quests()
    blocked = _snapshot(
        11, 11.0, base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, MENU_QUICK),
        observations=_rows(),
    )
    flow, _, actions, _ = _loop([blocked], initial)
    with pytest.raises(RuntimeWaitAborted):
        flow._wait_for_daily_tab(initial)
    # Only the tap from the clean pre-blocker state; the blocker frame
    # itself authorizes no input.
    assert actions.items == [SelectDailyQuests()]


def test_loop_aborts_on_foreign_resolved_state():
    initial = _clean_quests()
    foreign = _snapshot(11, 11.0, base=SCREEN_LOBBY)
    flow, _, actions, _ = _loop([foreign], initial)
    with pytest.raises(RuntimeWaitAborted):
        flow._wait_for_daily_tab(initial)
    assert actions.items == [SelectDailyQuests()]


# --- Safety: UNKNOWN / AMBIGUOUS ------------------------------------------

def test_unknown_and_ambiguous_wait_passively_without_input():
    initial = _clean_quests()
    unknown = _snapshot(11, 11.0, base=None)
    ambiguous = _snapshot(
        12, 12.0, base=None,
        status=ResolutionStatus.AMBIGUOUS,
        base_candidates=(SCREEN_LOBBY, SCREEN_QUESTS),
    )
    ready = _ready_daily(13, 13.0)
    flow, _, actions, _ = _loop([unknown, ambiguous, ready], initial)
    result = flow._wait_for_daily_tab(initial)
    assert result is ready
    assert actions.items == [SelectDailyQuests()]


# --- Progress Reward: separate contract ------------------------------------

def test_progress_available_is_not_fully_settled():
    frame = _ready_daily(2, 2.0, progress=True)
    assert not DailyQuestsFlow._is_daily_quests_fully_settled(frame)
    assert not DailyQuestsFlow._has_incompatible_daily_state(frame)


def test_progress_unavailable_is_fully_settled():
    frame = _ready_daily(2, 2.0)
    assert DailyQuestsFlow._is_daily_quests_fully_settled(frame)
    assert not DailyQuestsFlow._has_incompatible_daily_state(frame)


def test_progress_with_blocker_aborts_instead_of_settling():
    frame = _snapshot(
        2, 2.0, base=SCREEN_QUESTS,
        overlays=(
            MODE_DAILY_QUESTS,
            STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
            MENU_QUICK,
        ),
        observations=_rows(),
    )
    assert not DailyQuestsFlow._is_daily_quests_fully_settled(frame)
    assert DailyQuestsFlow._has_incompatible_daily_state(frame)
