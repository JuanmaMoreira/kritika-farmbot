"""Native blocker lost its config parent after Start in session 8212399d."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import pytest

from bot.arena_flow_reader import ArenaFlowReader, ArenaFlowVisuals
from bot.arena_reader import crop
from bot.ocr import RapidOcrEngine
from tests.test_arena_flow import World, flow

ROOT = Path(__file__).resolve().parents[1]
ENTRY = json.loads((ROOT/'tests/fixtures/arena_socket_native/manifest.json').read_text())['entries'][0]


@pytest.fixture
def native():
    path = ROOT/ENTRY['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ENTRY['sha256']
    image = cv2.imread(str(path))
    assert list(image.shape) == ENTRY['frame_shape']
    return image


def test_native_blocker_and_config_parent_are_both_positive(native):
    operation = flow(World())
    operation.v = ArenaFlowVisuals()
    assert operation._blocked(native)
    assert not operation.v.loading(native)


def test_bag_full_without_config_parent_cannot_credit_failed_start(native):
    operation = flow(World())
    operation.v = ArenaFlowVisuals()
    l, t, r, b = operation.v._specs['config_start']['roi']
    crop(native, (l-.005, t-.007, r+.005, b+.007))[:] = 0
    assert operation.v.has(native, 'bag_full')
    assert not operation._blocked(native)


@pytest.mark.parametrize('badges,corrupt,expected,active', [
    (71, False, 'socket_relief_unavailable', False),
    (72, False, 'blocked_start_lineage_uncertain', True),
    (71, True, 'blocked_start_lineage_uncertain', True),
])
def test_real_native_rejection_requires_unchanged_readable_badges(native, badges, corrupt, expected, active):
    from bot.arena_flow_reader import ECONOMY_ROIS
    if corrupt:
        crop(native, ECONOMY_ROIS[0])[:] = 0
    world = World()
    world.badges = badges
    world.block = True
    operation = flow(world)
    visuals = ArenaFlowVisuals()
    reader = ArenaFlowReader(RapidOcrEngine())
    original_has, original_loading = operation.v.has, operation.v.loading
    operation.v.has = lambda frame, name: (visuals.has(frame, name)
        if frame.shape == native.shape else original_has(frame, name))
    operation.v.loading = lambda frame: (visuals.loading(frame)
        if frame.shape == native.shape else original_loading(frame))
    operation.reader._integer = reader._integer
    refresh = world.refresh_native

    def capture():
        snapshot = refresh()
        return replace(snapshot, image=native.copy()) if world.surface == 'blocker' else snapshot

    world.refresh_native = capture
    result = operation.run()
    assert result.error == expected
    assert result.physical_operation_may_be_active is active
    assert world.start_count == 1 and result.metrics['inputs'][-1] == 'start'
