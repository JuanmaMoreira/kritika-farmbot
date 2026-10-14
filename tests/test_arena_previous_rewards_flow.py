"""Optional entry acknowledgment, using the acquired OK-to-selection transition."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.arena_actions import ArenaAction, ArenaControl as C
from bot.arena_config import ArenaMode
from bot.arena_flow import _Stop
from bot.arena_flow_reader import ArenaFlowVisuals
from bot.flow_contracts import FlowStatus
from tests.test_arena_flow import World, flow
from test_arena_b2 import ReturnWorld, SingleWorld, single_flow
from test_arena_farming_cycle import World as FarmingWorld

ROOT = Path(__file__).resolve().parents[1]


class PreviousWorld(World):
    states = World.states + ('previous_rewards',)

    def execute(self, action, geometry, **kwargs):
        super().execute(action, geometry, **kwargs)
        if self.no_effect is action.control:
            return
        if action.control is C.ARENA:
            self.surface = 'previous_rewards'
        elif action.control is C.PREVIOUS_REWARDS_OK:
            self.surface = 'selection'


@pytest.mark.parametrize('mode', [ArenaMode.AUTO_REPEAT, ArenaMode.SINGLE_BATTLE])
@pytest.mark.parametrize('present', [True, False])
def test_entry_acknowledgment_is_optional_before_requested_battle(mode, present):
    world = SingleWorld() if mode is ArenaMode.SINGLE_BATTLE else World()
    world.states += ('previous_rewards',)
    execute = world.execute

    def entry(action, geometry, **kwargs):
        execute(action, geometry, **kwargs)
        if action.control is C.ARENA and present:
            world.surface = 'previous_rewards'
        elif action.control is C.PREVIOUS_REWARDS_OK:
            world.surface = 'selection'

    world.execute = entry
    result = (single_flow(world) if mode is ArenaMode.SINGLE_BATTLE else flow(world)).run()
    assert result.succeeded
    route = [C.BATTLE, C.ARENA] + ([C.PREVIOUS_REWARDS_OK] if present else []) + [C.EASY]
    assert world.inputs[:len(route)] == route
    assert world.inputs.count(C.PREVIOUS_REWARDS_OK) == int(present)
    assert world.start_count == 1


def test_farming_cycle_uses_acknowledgment_in_existing_arena_owner():
    world = ReturnWorld()
    world.states += ('previous_rewards',)
    execute = world.execute

    def entry(action, geometry, **kwargs):
        execute(action, geometry, **kwargs)
        if action.control is C.ARENA:
            world.surface = 'previous_rewards'
        elif action.control is C.PREVIOUS_REWARDS_OK:
            world.surface = 'selection'

    world.execute = entry
    farming = FarmingWorld([(106, 0), (2, 0)])
    read = farming.read

    def resources_after_owner():
        resources = read()
        world.now = max(world.now, resources.observed_at) + 1.
        farming.now = world.now
        return replace(resources, observed_at=world.now)

    farming.read = resources_after_owner

    def arena(difficulty):
        operation = flow(world, return_context='screen.lobby')
        operation.difficulty = difficulty
        return operation

    farming.cycle.arena_factory = arena
    result = farming.cycle.run()
    assert result.succeeded, (result.error, result.termination, result.operations)
    assert len(result.operations) == 1
    assert result.operations[0].succeeded and world.surface == 'lobby'
    assert world.inputs.count(C.PREVIOUS_REWARDS_OK) == 1 and world.start_count == 1
    assert farming.trace == ['read', 'lobby', 'read']  # No MW/Manual/Mailbox work.


def test_unconfirmed_close_is_not_retried_and_does_not_select_or_start():
    world = PreviousWorld()
    world.no_effect = C.PREVIOUS_REWARDS_OK
    result = flow(world).run()
    assert result.error == 'transition_unconfirmed'
    assert world.inputs == [C.BATTLE, C.ARENA, C.PREVIOUS_REWARDS_OK]
    assert world.start_count == 0 and not result.physical_operation_may_be_active


@pytest.mark.parametrize('after', ['unknown', 'ranking'])
def test_close_without_credited_selection_stops_before_difficulty(after):
    world = PreviousWorld()
    execute = world.execute

    def uncredited(action, geometry, **kwargs):
        execute(action, geometry, **kwargs)
        if action.control is C.PREVIOUS_REWARDS_OK:
            world.surface = after

    world.execute = uncredited
    result = flow(world).run()
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.error == 'transition_unconfirmed'
    assert world.inputs == [C.BATTLE, C.ARENA, C.PREVIOUS_REWARDS_OK]
    assert world.start_count == 0


@pytest.mark.parametrize('control', [C.ARENA, C.PREVIOUS_REWARDS_OK])
def test_cancel_before_or_after_acknowledgment_stops_without_extra_input(control):
    world = PreviousWorld()
    world.cancel_on = control
    result = flow(world).run()
    assert result.status is FlowStatus.CANCELLED
    assert world.inputs[-1] is control and world.start_count == 0


def test_stale_positive_modal_does_not_authorize_ok():
    world = PreviousWorld()
    operation = flow(world)
    predicate = operation.v.previous_rewards

    def slow_predicate(frame):
        matched = predicate(frame)
        if matched:
            world.now += operation.reader.max_age + 1.
        return matched

    operation.v.previous_rewards = slow_predicate
    result = operation.run()
    assert result.error == 'action_source_stale'
    assert world.inputs == [C.BATTLE, C.ARENA] and world.start_count == 0


@pytest.mark.parametrize('modal', ['previous_rewards_02', 'ok_before_01', 'world_boss_season_negative'])
def test_real_pixels_wired_into_navigation(modal):
    world = PreviousWorld()
    images = {
        'lobby': 'arena_previous_rewards/lobby_before_01',
        'select_mode': 'arena_previous_rewards/select_mode_before_01',
        'previous_rewards': f'arena_previous_rewards/{modal}',
        'selection': 'arena_previous_rewards/ok_after_01',
        'challenge': 'arena_b2/challenge_native_off',
    }
    frames = {state: cv2.imread(str(ROOT/f'tests/fixtures/{name}.png'))
              for state, name in images.items()}
    assert all(frame is not None for frame in frames.values())
    world.image = lambda: frames[world.surface].copy()
    operation = flow(world)
    operation.v = operation.reader.visuals = ArenaFlowVisuals()

    def stop_before_preparation(before):
        raise _Stop('navigation_verified')

    operation._prepare = stop_before_preparation
    result = operation.run()
    if modal == 'world_boss_season_negative':
        assert result.error == 'transition_unconfirmed'
        assert world.inputs == [C.BATTLE, C.ARENA]
    else:
        assert result.error == 'navigation_verified'
        assert world.inputs == [C.BATTLE, C.ARENA, C.PREVIOUS_REWARDS_OK, C.EASY]
    assert world.start_count == 0


def test_previous_ok_executor_uses_acquired_center_and_frame_geometry():
    image = cv2.imread(str(ROOT/'tests/fixtures/arena_previous_rewards/ok_before_01.png'))
    geometry = FrameGeometry.from_frame(image)
    taps = []
    executor = ActionExecutor(SimpleNamespace(tap=lambda x, y: taps.append((x, y))))
    executor.execute(ArenaAction(C.PREVIOUS_REWARDS_OK), geometry)
    assert taps == [(round(.5*image.shape[1]), round(.8215*image.shape[0]))]
