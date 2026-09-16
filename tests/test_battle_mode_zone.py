"""BattleModeZone.leave lobby-return waits with real VerifiedTransition.

Covers the HIL false abort: after SelectQuickMenuLobby, a transient
RESOLVED screen.battle_mode_select + status.monster_wave_daily_active must be
tolerated while waiting (no abort, no retry, no second tap) until clean Lobby.
"""

import numpy as np

from bot.action_executor import FrameGeometry
from bot.battle_mode_zone import BattleModeZone
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    POPUP_SOCKET_INVENTORY_FULL,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.flow_contracts import FlowStatus
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition


def snapshot(sequence, *, base=None, overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    timestamp = float(sequence)
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, ()),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=overlays,
            base_candidates=(
                (SCREEN_LOBBY, SCREEN_GUILD)
                if status is ResolutionStatus.AMBIGUOUS else ()
            ),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def battle(sequence, overlays=()):
    return snapshot(sequence, base=SCREEN_BATTLE_MODE_SELECT, overlays=overlays)


def menu(sequence):
    return snapshot(
        sequence, base=SCREEN_BATTLE_MODE_SELECT, overlays=(MENU_QUICK,)
    )


def lobby(sequence, overlays=()):
    return snapshot(sequence, base=SCREEN_LOBBY, overlays=overlays)


class ScriptedObserver:
    """Replay one scripted frame window per wait_until call."""

    def __init__(self, waits, observes=()):
        self._waits = list(waits)
        self._observes = list(observes)

    def wait_until(
        self, condition, *, after_sequence, timeout, abort_if=None,
        cancel_requested=None, stable_for=0.0,
    ):
        frames = self._waits.pop(0)
        last = None
        for frame in frames:
            assert frame.sequence > after_sequence
            last = frame
            if abort_if is not None and abort_if(frame):
                raise RuntimeWaitAborted(frame)
            if condition(frame):
                return frame
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence, timeout=timeout,
            last_snapshot=last,
        )

    def observe(self):
        return self._observes.pop(0)


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append(type(action).__name__)

    def taps(self, name):
        return sum(1 for call in self.calls if call == name)


def run_leave(waits, observes=()):
    observer = ScriptedObserver(waits, observes)
    actions = Actions()
    zone = BattleModeZone(observer, VerifiedTransition(observer, actions))
    return zone.leave(), actions


def test_transient_source_with_daily_badge_does_not_abort_or_retry():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [
            battle(3, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,)),
            battle(4, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,)),
            lobby(5),
        ],
    ])

    assert result.status is FlowStatus.COMPLETED
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 1
    assert result.transition_outcomes[-1] == (
        "battle_mode.select_lobby", "success_first_attempt",
    )
    assert result.transition_attempts[-1] == ("battle_mode.select_lobby", 1, 0)


def test_persistent_source_fails_bounded_without_second_tap():
    result, actions = run_leave(
        [
            [battle(1)],
            [menu(2)],
            [
                battle(3, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,)),
                battle(4, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,)),
            ],
            [],
        ],
        observes=[battle(5, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,))],
    )

    assert result.status is FlowStatus.FAILED
    assert "retry_guard_rejected" in result.error
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_foreign_resolved_state_aborts_without_retry():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [snapshot(3, base=SCREEN_GUILD)],
    ])

    assert result.status is FlowStatus.FAILED
    assert "unexpected_state" in result.error
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_transient_unknown_waits_for_lobby_without_extra_input():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [snapshot(3), lobby(4)],
    ])

    assert result.status is FlowStatus.COMPLETED
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_persistent_unknown_fails_closed_without_retry():
    result, actions = run_leave(
        [[battle(1)], [menu(2)], [snapshot(3)], []],
        observes=[snapshot(4)],
    )

    assert result.status is FlowStatus.FAILED
    assert "retry_guard_rejected" in result.error
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_ambiguous_origin_frame_aborts_without_retry():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [snapshot(3, status=ResolutionStatus.AMBIGUOUS)],
    ])

    assert result.status is FlowStatus.FAILED
    assert "unexpected_state" in result.error
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_lobby_with_blocker_is_not_a_false_success():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [lobby(3, (POPUP_SOCKET_INVENTORY_FULL,))],
    ])

    assert result.status is FlowStatus.FAILED
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_source_then_menu_persistence_authorizes_exactly_one_retry():
    result, actions = run_leave(
        [
            [battle(1)],
            [menu(2)],
            [battle(3, (STATUS_MONSTER_WAVE_DAILY_ACTIVE,)), menu(4)],
            [],
            [lobby(6)],
        ],
        observes=[menu(5)],
    )

    assert result.status is FlowStatus.COMPLETED
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 2
    assert result.transition_outcomes[-1] == (
        "battle_mode.select_lobby", "success_after_retry",
    )


def test_world_boss_badge_source_is_also_tolerated():
    result, actions = run_leave([
        [battle(1)],
        [menu(2)],
        [battle(3, (STATUS_WORLD_BOSS_DAILY_ACTIVE,)), lobby(4)],
    ])

    assert result.status is FlowStatus.COMPLETED
    assert actions.taps("SelectQuickMenuLobby") == 1
