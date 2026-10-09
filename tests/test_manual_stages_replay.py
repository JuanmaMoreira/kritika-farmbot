"""Small portable regression pixels; the wider incremental corpus stays local."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from bot.manual_stages_reader import ManualStagesDetector,auto_window_state
from bot.catalog import build_default_resolver
from bot.observations import ObservationBatch
from bot.state import ResolutionStatus

ROOT=Path(__file__).parent/'fixtures/manual_stages_controls'
MANIFEST=json.loads((ROOT/'manifest.json').read_text())

def frame(name):
    entry=MANIFEST[name];image=np.zeros(entry['shape'],dtype=np.uint8);h,w=image.shape[:2]
    for region in entry['regions']:
        path=ROOT/region['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==region['sha256']
        x1,y1,x2,y2=region['roi']
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(path))
    return image

@pytest.mark.parametrize('name,expected',[
    ('penance_relief_stream',True),('penance_relief_native',True),
    ('penance_on_prior',True),('penance_off_hell',False)])
def test_penance_after_inventory_relief_and_prior_states(name,expected):
    detector=ManualStagesDetector();image=frame(name)
    assert detector.toggle(image,'penance') is expected
    # A selected control behind another modal cannot authorize a tap.
    assert detector.toggle((image*.5).astype(np.uint8),'penance') is None

@pytest.mark.parametrize('name',['auto_off_monk','auto_on','clear','death','death_guide'])
def test_penance_relief_variant_does_not_match_other_surfaces(name):
    assert not ManualStagesDetector().present(frame(name),'penance_on_relief')

@pytest.mark.parametrize('name,expected',[('auto_off_monk',False),('auto_on',True)])
def test_real_auto_border_regression(name,expected):
    detector=ManualStagesDetector();image=frame(name)
    assert detector.battle(image) and detector.terminal(image) is None
    value=detector.auto_glow(image)
    assert auto_window_state([(i*.1,value) for i in range(21)]) is expected

@pytest.mark.parametrize('name,overlay',[('clear','overlay.manual_stage_clear'),
    ('death','popup.stages_death'),('death_guide','popup.stages_death_guide')])
def test_positive_terminal_layering_distinct_from_stage_modal(name,overlay):
    detector=ManualStagesDetector();image=frame(name)
    assert detector.terminal(image)==name and detector.auto_glow(image) is None
    state=build_default_resolver().resolve(ObservationBatch(1,0.,detector.detect(image)))
    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context=='screen.manual_stage_battle' and tuple(state.overlays)==(overlay,)

def test_loading_and_unknown_do_not_authorize_terminal_or_auto():
    detector=ManualStagesDetector()
    entry=MANIFEST['clear'];image=np.zeros(entry['shape'],dtype=np.uint8)
    profile=detector.profile['loading'];h,w=image.shape[:2];x1,y1,x2,y2=profile['crop']
    template=detector._templates['loading']
    y,x=round(y1*h),round(x1*w)
    image[y:y+template.shape[0],x:x+template.shape[1]]=template
    assert detector.terminal(image) is None and detector.auto_glow(image) is None
    assert [o.name for o in detector.detect(image)]==['stages.loading']
