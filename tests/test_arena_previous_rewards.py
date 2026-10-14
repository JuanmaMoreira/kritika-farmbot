"""Acquired modal identity, layering and nearby physical negatives; no claim."""
import hashlib
import json
from pathlib import Path
import cv2
import pytest
from bot.arena_reader import ArenaDetector, crop
from bot.arena_semantics import ARENA_PREVIOUS_REWARDS, POPUP_ARENA_PREVIOUS_REWARDS
from bot.catalog import build_default_resolver
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.perception import build_arena_perception, build_default_perception

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads((ROOT/'tests/fixtures/arena_previous_rewards/manifest.json').read_text(encoding='utf8'))


@pytest.fixture(scope='module')
def detector():return ArenaDetector()


@pytest.mark.parametrize('entry',MANIFEST['entries'],ids=lambda e:Path(e['path']).stem)
def test_acquired_identity_and_modal_layer(entry,detector):
    path=ROOT/entry['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    frame=cv2.imread(str(path))
    observations=detector.detect(frame)
    assert (ARENA_PREVIOUS_REWARDS in {o.name for o in observations})==entry['expected_previous_rewards']
    state=build_default_resolver().resolve(ObservationBatch(1,100.,observations))
    assert (POPUP_ARENA_PREVIOUS_REWARDS in state.overlays)==entry['expected_previous_rewards']
    if entry['expected_previous_rewards']:
        assert state.overlays==(POPUP_ARENA_PREVIOUS_REWARDS,)
        # Occluded selection cannot be invented from the modal's Arena wording.
        assert state.base_context is None
    if entry.get('physical_state')=='arena_selection':
        assert state.base_context=='screen.arena'
        assert not state.overlays


@pytest.mark.parametrize('scale',[1.,2.])
def test_shape_scaled_replay_and_variable_fields_do_not_gate_eligibility(detector,scale):
    entry=next(e for e in MANIFEST['entries'] if e['expected_previous_rewards'])
    frame=cv2.imread(str(ROOT/entry['path']))
    # SYNTHETIC software masks: no extra physical eligibility/season evidence.
    for roi in ((.34,.336,.432,.380),(.35,.468,.458,.513),(.222,.543,.782,.700)):
        crop(frame,roi)[:]=0
    h,w=frame.shape[:2]
    frame=cv2.resize(frame,(round(w*scale),round(h*scale)))
    assert ARENA_PREVIOUS_REWARDS in {o.name for o in detector.detect(frame)}


def test_shared_mailbox_footer_and_ok_alone_are_not_arena_authority(detector):
    entry=next(e for e in MANIFEST['entries'] if e['expected_previous_rewards'])
    frame=cv2.imread(str(ROOT/entry['path']))
    crop(frame,(.434,.336,.660,.380))[:]=0
    assert ARENA_PREVIOUS_REWARDS not in {o.name for o in detector.detect(frame)}


def test_previous_assets_provenance():
    data=json.loads((ROOT/'datasets/arena_previous_rewards_assets_manifest.json').read_text(encoding='utf8'))
    for spec in data['assets']:
        assert hashlib.sha256((ROOT/spec['path']).read_bytes()).hexdigest()==spec['sha256']
        assert spec['source'].startswith('screencaps/semantic/arena-previous-rewards/')


@pytest.mark.parametrize('builder',[build_arena_perception,build_default_perception])
def test_existing_perception_wiring_distinguishes_foreign_season_modals(builder):
    entry=next(e for e in MANIFEST['entries'] if e['expected_previous_rewards'])
    frame=cv2.imread(str(ROOT/entry['path']))
    # Default legacy templates require native-sized search regions. Restore
    # acquired dimensions from the portable copy; no global CV change here.
    h,w=frame.shape[:2]
    frame=cv2.resize(frame,(w*2,h*2),interpolation=cv2.INTER_LINEAR)
    batch=builder(ROOT).analyze(FrameSnapshot(frame,100.,1))
    state=build_default_resolver().resolve(batch)
    assert POPUP_ARENA_PREVIOUS_REWARDS in state.overlays
    assert 'popup.world_boss_previous_rewards' not in state.overlays
    assert 'popup.monster_wave_weekly_results' not in state.overlays
    assert 'popup.arena_batch_result' not in state.overlays
