"""ProductiveRuntime._navigate_to_guild return semantics.

Drives the helper with a real VerifiedTransition and scripted frames,
mirroring tests/test_productive_quick_menu_lobby.py. The helper's only
productive caller is MinimalPreconditionEnsurer.ensure() for
EXACT_STATE screen.guild: Lobby routes to _navigate_lobby_to_guild
(direct), Guild is already satisfied, Battle Mode Select is not
quick-menu-accessible, and the helper gate rejects Lobby/None/unclean.
The helper therefore serves exactly three origins: screen.world_boss,
screen.pets_manage and screen.pet_summon (Pets origins use Quick Menu
here, unlike the Lobby return which closes Pets directly).

Contract under test (unchanged timings: 6s normal / 2s grace / max 2 /
stable 0.25, clean-Guild destination):
- contractual source persisting post-tap is tolerated while waiting:
  not success, not abort, not a retry on its own, no second tap;
- the handoff must stay valid through that transient so a later menu frame
  can still authorize exactly one bounded retry;
- menu persistence authorizes a bounded retry only via handoff.allows();
- clean source without menu never retries;
- foreign RESOLVED aborts; UNKNOWN never inputs/retries; AMBIGUOUS aborts;
- Guild with a blocker is never success;
- any recovery invalidates the handoff (no provenance reuse).
"""

import numpy as np

import bot.productive_runtime as productive_module
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    POPUP_SOCKET_INVENTORY_FULL,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
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


GUILD_CLEAN_OVERLAYS = (
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
)
PET_SUMMON_CLEAN_OVERLAYS = (
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
)
PETS_MANAGE_CLEAN_OVERLAYS = (STATUS_PET_SUMMON_DAILY_ACTIVE,)


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


def guild(sequence, overlays=GUILD_CLEAN_OVERLAYS):
    return snapshot(sequence, base=SCREEN_GUILD, overlays=overlays)


def world_boss(sequence):
    return snapshot(sequence, base=SCREEN_WORLD_BOSS)


def pet_summon(sequence):
    return snapshot(
        sequence, base=SCREEN_PET_SUMMON, overlays=PET_SUMMON_CLEAN_OVERLAYS,
    )


def pets_manage(sequence):
    return snapshot(
        sequence, base=SCREEN_PETS_MANAGE, overlays=PETS_MANAGE_CLEAN_OVERLAYS,
    )


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


def run_helper(initial, waits, observes=()):
    observer = ScriptedObserver(waits, [initial, *observes])
    actions = Actions()
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
        runtime._navigate_to_guild(),
        actions,
    )


def test_clean_success_world_boss():
    succeeded, actions = run_helper(world_boss(1), [[menu(2)], [guild(3)]])

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_clean_success_pet_summon():
    succeeded, actions = run_helper(pet_summon(1), [[menu(2)], [guild(3)]])

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_clean_success_pets_manage_with_daily():
    succeeded, actions = run_helper(pets_manage(1), [[menu(2)], [guild(3)]])

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_contractual_source_persists_pet_summon_without_abort_or_retry():
    succeeded, actions = run_helper(
        pet_summon(1),
        [[menu(2)], [pet_summon(3), pet_summon(4), guild(5)]],
    )

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_contractual_source_persists_world_boss_without_abort_or_retry():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), world_boss(4), guild(5)]],
    )

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_source_then_menu_persistence_authorizes_exactly_one_retry():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), menu(4)], [], [guild(6)]],
        observes=[menu(5)],
    )

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 2


def test_pet_summon_source_then_menu_authorizes_exactly_one_retry():
    succeeded, actions = run_helper(
        pet_summon(1),
        [[menu(2)], [pet_summon(3), menu(4)], [], [guild(6)]],
        observes=[menu(5)],
    )

    assert succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 2


def test_persistent_source_without_menu_fails_bounded_without_second_tap():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [world_boss(3), world_boss(4)], []],
        observes=[world_boss(5)],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_persistent_pet_summon_without_menu_never_retries():
    succeeded, actions = run_helper(
        pet_summon(1),
        [[menu(2)], [pet_summon(3), pet_summon(4)], []],
        observes=[pet_summon(5)],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_foreign_resolved_state_aborts_without_retry():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [lobby(3)]],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_transient_unknown_waits_for_guild_without_extra_input():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3), guild(4)]],
    )

    assert succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_persistent_unknown_fails_closed_without_retry():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3)], []],
        observes=[snapshot(4)],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_ambiguous_frame_aborts_without_retry():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [snapshot(3, status=ResolutionStatus.AMBIGUOUS)]],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_guild_with_blocker_is_not_a_false_success():
    succeeded, actions = run_helper(
        world_boss(1),
        [[menu(2)], [guild(3, (*GUILD_CLEAN_OVERLAYS, POPUP_SOCKET_INVENTORY_FULL))]],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 1


def test_foreign_menu_aborts_open_without_guild_tile():
    succeeded, actions = run_helper(
        world_boss(1),
        [[snapshot(2, base=SCREEN_GUILD, overlays=(MENU_QUICK,))]],
    )

    assert not succeeded
    assert actions.taps("OpenQuickMenu") == 1
    assert actions.taps("SelectQuickMenuGuild") == 0


def test_lobby_origin_rejected_without_input():
    succeeded, actions = run_helper(
        lobby(1),
        [],
    )

    assert not succeeded
    assert actions.taps("OpenQuickMenu") == 0
    assert actions.taps("SelectQuickMenuGuild") == 0


def test_open_recovery_invalidates_handoff_provenance(monkeypatch):
    class Recovery:
        def __init__(self, cleaned):
            self.cleaned = cleaned

        def attempt(self, snapshot, expected):
            assert not expected(snapshot)
            return self.cleaned

    monkeypatch.setattr(
        productive_module.ProductiveRuntime,
        "build_obstruction_recovery",
        lambda self: Recovery(menu(4)),
    )
    succeeded, actions = run_helper(
        world_boss(1),
        [[world_boss(2)], []],
        observes=[world_boss(3)],
    )

    assert not succeeded
    assert actions.taps("SelectQuickMenuGuild") == 0
