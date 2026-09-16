"""ProductiveRuntime._quick_menu_to_lobby return semantics.

Drives the shared helper with a real VerifiedTransition and scripted frames,
mirroring tests/test_battle_mode_zone.py. The helper's only productive caller
is ProductiveRuntime._navigate_to_lobby, whose gate restricts origins to
quick-menu-accessible clean bases; Pets origins use ClosePets instead, Lobby
returns early, and Battle Mode Select is not accessible. The helper therefore
serves exactly two origins: screen.guild and screen.world_boss.

Contract under test (unchanged timings: 6s normal / 2s grace / max 2 /
stable 0.25, QUICK_MENU_TO_LOBBY_SCOPE, clean-Lobby B2 destination):
- contractual source persisting post-tap is tolerated while waiting:
  not success, not abort, not a retry on its own, no second tap;
- the handoff must stay valid through that transient so a later menu frame
  can still authorize exactly one bounded retry;
- menu persistence authorizes a bounded retry only via handoff.allows();
- clean source without menu never retries;
- foreign RESOLVED aborts; UNKNOWN never inputs/retries; AMBIGUOUS aborts;
- Lobby with a blocker is never success;
- any recovery invalidates the handoff (no provenance reuse).
"""

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    POPUP_SOCKET_INVENTORY_FULL,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
)
from bot.observations import ObservationBatch
from bot.productive_runtime import ProductiveRuntime
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition, VerifiedTransitionOutcome, VerifiedTransitionPolicy


GUILD_CLEAN_OVERLAYS = (
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
)
POLICY = VerifiedTransitionPolicy(
    normal_timeout=6.0, grace_timeout=2.0, max_attempts=2,
)


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


def guild(sequence):
    return snapshot(sequence, base=SCREEN_GUILD, overlays=GUILD_CLEAN_OVERLAYS)


def world_boss(sequence):
    return snapshot(sequence, base=SCREEN_WORLD_BOSS)


def menu(sequence, *, base=None):
    return snapshot(sequence, base=base, overlays=(MENU_QUICK,))


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


class Events:
    def record(self, event, **fields):
        pass


def run_helper(initial, waits, observes=(), recovery=None):
    observer = ScriptedObserver(waits, observes)
    actions = Actions()
    transition = VerifiedTransition(
        observer, actions, Events(), recovery,
    )
    runtime = ProductiveRuntime(
        config=object(),
        observer=observer,
        actions=actions,
        facts=object(),
        auto_battle=object(),
        socket_relief=object(),
        equipment_combine_relief=object(),
        pet_summon_space_relief=object(),
        events=Events(),
        cancel_token=__import__("types").SimpleNamespace(
            is_requested=lambda: False,
        ),
    )
    return (
        runtime._quick_menu_to_lobby(initial, transition, POLICY),
        actions,
    )


def test_clean_success_world_boss():
    result, actions = run_helper(world_boss(1), [[menu(2)], [lobby(3)]])

    assert result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_clean_success_guild():
    result, actions = run_helper(guild(1), [[menu(2)], [lobby(3)]])

    assert result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_contractual_source_persists_world_boss_without_abort_or_retry():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), world_boss(4), lobby(5)]],
    )

    assert result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_contractual_source_persists_guild_without_abort_or_retry():
    result, actions = run_helper(
        guild(1),
        [[menu(2)], [guild(3), guild(4), lobby(5)]],
    )

    assert result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_source_then_menu_persistence_authorizes_exactly_one_retry():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), menu(4)], [], [lobby(6)]],
        observes=[menu(5)],
    )

    assert result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 2


def test_persistent_source_without_menu_fails_bounded_without_second_tap():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), world_boss(4)], []],
        observes=[world_boss(5)],
    )

    assert not result.succeeded
    assert "retry_guard_rejected" in (result.error or "")
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_persistent_guild_source_without_menu_never_retries():
    result, actions = run_helper(
        guild(1),
        [[menu(2)], [guild(3), guild(4)], []],
        observes=[guild(5)],
    )

    assert not result.succeeded
    assert "retry_guard_rejected" in (result.error or "")
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_foreign_resolved_state_aborts_without_retry():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [guild(3)]],
    )

    assert not result.succeeded
    assert result.outcome is VerifiedTransitionOutcome.UNEXPECTED_STATE
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_transient_unknown_waits_for_lobby_without_extra_input():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3), lobby(4)]],
    )

    assert result.succeeded
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_persistent_unknown_fails_closed_without_retry():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3)], []],
        observes=[snapshot(4)],
    )

    assert not result.succeeded
    assert "retry_guard_rejected" in (result.error or "")
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_ambiguous_frame_aborts_without_retry():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3, status=ResolutionStatus.AMBIGUOUS)]],
    )

    assert not result.succeeded
    assert result.outcome is VerifiedTransitionOutcome.UNEXPECTED_STATE
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_lobby_with_blocker_is_not_a_false_success():
    result, actions = run_helper(
        world_boss(1),
        [[menu(2)], [lobby(3, (POPUP_SOCKET_INVENTORY_FULL,))]],
    )

    assert not result.succeeded
    assert actions.taps("SelectQuickMenuLobby") == 1


def test_foreign_menu_aborts_open_without_lobby_tile():
    result, actions = run_helper(
        world_boss(1),
        [[snapshot(2, base=SCREEN_GUILD, overlays=(MENU_QUICK,))]],
    )

    assert not result.succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuLobby") == 0


def test_open_recovery_invalidates_handoff_provenance():
    class Recovery:
        def __init__(self, cleaned):
            self.cleaned = cleaned

        def attempt(self, snapshot, expected):
            assert not expected(snapshot)
            return self.cleaned

    result, actions = run_helper(
        world_boss(1),
        [[world_boss(2)], []],
        observes=[world_boss(3)],
        recovery=Recovery(menu(4)),
    )

    assert not result.succeeded
    assert result.error == "quick_menu_origin_handoff_invalid"
    assert actions.taps("SelectQuickMenuLobby") == 0
