"""SKIP result with the Points Reward MODAL: recognize, ACK only its OK,
fresh snapshot, then normal CLEAR handling. No device, no ADB."""
from pathlib import Path

import pytest

from bot.catalog import OVERLAY_RULES
from bot.geometry import relative_point_to_pixel
from bot.monster_wave_actions import (
    AcknowledgeMonsterWaveClear,
    AcknowledgeMonsterWavePointsReward,
    MONSTER_WAVE_TARGETS,
)
from bot.monster_wave_activity import popup
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_semantics import (
    MW_POINTS_REWARD,
    POPUP_MW_CLEAR,
    POPUP_MW_POINTS_REWARD,
    MW_OVERLAY_LANDMARKS,
    SCREEN_MONSTER_WAVE,
)
from bot.observations import Observation, ObservationSource
from bot.perception.monster_wave import MONSTER_WAVE_SPECS
from bot.state import ResolutionStatus
from test_monster_wave import Device
from test_world_boss_flow import snapshot


class PointsDevice(Device):
    """Device whose SKIP result raises Points Reward above CLEAR (USER_GT order)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.geometries = {}

    def execute(self, action, geometry):
        if isinstance(action, AcknowledgeMonsterWavePointsReward):
            kind = type(action).__name__
            self.intents.append(kind)
            self.trace.append(('intent', kind))
            self.geometries[kind] = geometry
            self.executor.execute(action, geometry)
            # USER_GT: OK dismisses Points Reward and CLEAR lies underneath.
            self.overlays = (POPUP_MW_CLEAR,)
            self.names = ()
            return
        return super().execute(action, geometry)


def test_points_reward_is_modal_popup_paired_with_its_landmark():
    assert POPUP_MW_POINTS_REWARD == "popup.monster_wave_points_reward"
    assert not POPUP_MW_POINTS_REWARD.startswith("overlay.")
    assert (POPUP_MW_POINTS_REWARD, MW_POINTS_REWARD) in MW_OVERLAY_LANDMARKS
    rule = next(r for r in OVERLAY_RULES if r.name == POPUP_MW_POINTS_REWARD)
    assert rule.requires == (MW_POINTS_REWARD,)


def test_points_reward_detector_uses_stable_title_landmark():
    spec = next(s for s in MONSTER_WAVE_SPECS if s.name == MW_POINTS_REWARD)
    assert (spec.asset_path.parent / spec.asset_path.name).as_posix().endswith(
        "landmarks/monster-wave/monster_wave_points_reward.png")
    assert Path("assets/ui/landmarks/monster-wave/monster_wave_points_reward.png").is_file()
    # Title banner band only: the variable reward line lives in the dialog
    # body below, so identity never depends on reward text or amounts.
    left, top, right, bottom = spec.region
    assert top >= 0.10 and bottom <= 0.35 and left >= 0.35 and right <= 0.65
    assert 0.0 <= spec.calibration.negative_anchor < spec.calibration.positive_anchor <= 1.0


def test_points_reward_popup_needs_resolved_mw_base():
    assert popup(POPUP_MW_POINTS_REWARD)(
        snapshot(1, base=SCREEN_MONSTER_WAVE, overlays=(POPUP_MW_POINTS_REWARD,)))


@pytest.mark.parametrize('state', [ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS])
def test_unresolved_points_reward_never_authorizes_ack(state):
    s = snapshot(1, base=None, status=state,
                 overlays=(POPUP_MW_POINTS_REWARD,),
                 semantic_observations=(Observation(MW_POINTS_REWARD, 1.0, ObservationSource.LOCAL_CV),))
    assert not popup(POPUP_MW_POINTS_REWARD)(s)


def test_foreign_points_reward_never_authorizes_ack():
    s = snapshot(1, base="screen.lobby", overlays=(POPUP_MW_POINTS_REWARD,))
    assert not popup(POPUP_MW_POINTS_REWARD)(s)


def test_points_reward_then_clear_completes_without_waiting():
    d = PointsDevice(boundary="popup.monster_wave_inventory_board",
                     board_after=POPUP_MW_POINTS_REWARD)
    now = [0.0]
    sleeps = []
    activity = d.activity(config=MonsterWaveConfig(continue_when_nonblocking_inventory_full=True))
    activity.clock = lambda: now[0]
    activity.sleeper = lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds))
    result = activity.run()
    assert result.succeeded
    assert result.event_count('monster_wave.completed') == 1
    # Points Reward is handled immediately: no polling sleeps are consumed.
    assert sleeps == []
    ack_points = d.intents.index('AcknowledgeMonsterWavePointsReward')
    ack_clear = d.intents.index('AcknowledgeMonsterWaveClear')
    # CLEAR is never touched while Points Reward is on top.
    assert ack_points < ack_clear
    assert d.intents.count('AcknowledgeMonsterWavePointsReward') == 1
    # The ACK step demands a fresh snapshot before CLEAR handling resumes.
    segment = d.trace[d.trace.index(('intent', 'AcknowledgeMonsterWavePointsReward')):
                      d.trace.index(('intent', 'AcknowledgeMonsterWaveClear'))]
    assert any(item[0] == 'observe' for item in segment)


def test_points_reward_ack_taps_only_its_measured_ok():
    d = PointsDevice(boundary="popup.monster_wave_inventory_board",
                     board_after=POPUP_MW_POINTS_REWARD)
    result = d.activity(config=MonsterWaveConfig(continue_when_nonblocking_inventory_full=True)).run()
    assert result.succeeded
    assert MONSTER_WAVE_TARGETS[AcknowledgeMonsterWavePointsReward] == (.500, .656)
    geometry = d.geometries['AcknowledgeMonsterWavePointsReward']
    expected = relative_point_to_pixel((.500, .656), geometry.width, geometry.height)
    taps = [item[1] for item in d.trace if item[0] == 'tap']
    assert tuple(expected) in [tuple(pixel) for pixel in taps]


def test_normal_skip_clear_path_has_no_points_ack():
    d = PointsDevice(boundary=POPUP_MW_CLEAR)
    result = d.activity().run()
    assert result.succeeded
    assert result.event_count('monster_wave.completed') == 1
    assert 'AcknowledgeMonsterWavePointsReward' not in d.intents
    assert d.intents.count('AcknowledgeMonsterWaveClear') == 1


def test_native_points_title_and_post_ack_clear_are_distinct():
    import cv2
    from bot.capture import FrameSnapshot
    from bot.catalog import build_default_resolver
    from bot.perception import build_default_perception
    root = Path(__file__).resolve().parents[1]
    perception = build_default_perception(root)
    resolver = build_default_resolver()
    for file, expected in [("point_native_before",POPUP_MW_POINTS_REWARD),
                           ("point_native_after",POPUP_MW_CLEAR)]:
        image = cv2.imread(str(root/"artifacts/mw_stabilization"/(file+".png")))
        assert image is not None
        batch = perception.analyze(FrameSnapshot(image,1.,1))
        state = resolver.resolve(batch)
        assert state.status is ResolutionStatus.RESOLVED
        assert state.base_context == SCREEN_MONSTER_WAVE
        assert state.overlays == (expected,)
