from pathlib import Path
import cv2
import pytest
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.perception.socket import SocketEnhanceAnimationDetector
from bot.resolver import ContextResolver
from bot.runtime_observer import RuntimeObserver, RuntimeWaitTimeout
from bot.socket_inventory_relief import _is_tappable_animation

ROOT = Path(__file__).parent / 'fixtures/socket_animation_live'

@pytest.mark.parametrize('name,positive', [('frame_2147.png', True), ('frame_2153.png', True), ('frame_2159.png', False), ('clean-after.png', False)])
def test_live_animation_frames_keep_existing_detector_boundary(name, positive):
    frame = cv2.imread(str(ROOT / name))
    assert frame is not None
    assert bool(SocketEnhanceAnimationDetector().detect(frame)) is positive

def test_first_positive_can_handoff_before_flash_without_stability_gate():
    class Source:
        def __init__(self): self.n = 0
        def get_frame(self):
            self.n += 1
            name = 'frame_2147.png' if self.n == 1 else 'frame_2159.png'
            return FrameSnapshot(cv2.imread(str(ROOT/name)), self.n * .1, self.n)
    class Perception:
        def analyze(self, frame):
            return ObservationBatch(frame.sequence, frame.timestamp, SocketEnhanceAnimationDetector().detect(frame.image))
    class Clock:
        t = 0
        def now(self): return self.t
        def sleep(self, dt): self.t += dt
    def observer():
        c=Clock()
        return RuntimeObserver(Source(), Perception(), ContextResolver(), poll_interval=.1, clock=c.now, sleeper=c.sleep)
    # Reproduce the red gate with the actual positive/flash pixels.
    with pytest.raises(RuntimeWaitTimeout):
        observer().wait_until(_is_tappable_animation, after_sequence=0, timeout=.5, stable_for=.25)
    positive=observer().wait_until(_is_tappable_animation, after_sequence=0, timeout=.5, stable_for=0)
    assert positive.sequence == 1


def test_live_safe_taps_at_point_two_and_flash_has_zero_input_until_stable_base():
    from dataclasses import replace
    from bot.action_executor import FrameGeometry
    from bot.runtime_observer import RuntimeSnapshot, RuntimeFacts
    from bot.state import ResolvedState, ResolutionStatus
    from bot.tap_through_animation import TapThroughAnimation, TapThroughPolicy
    from bot.socket_inventory_relief import _is_clean_socket
    from unittest.mock import Mock
    frames=[]
    for i,(name,stamp) in enumerate([
        ('frame_2147.png',0.), ('frame_2159.png',.21),
        ('frame_2153.png',.22), ('clean-after.png',.43),
        ('clean-after.png',.55), ('clean-after.png',.71)],1):
        f=cv2.imread(str(ROOT/name));complete=name=='clean-after.png'
        observations=SocketEnhanceAnimationDetector().detect(f)
        frames.append(RuntimeSnapshot(FrameSnapshot(f,stamp,i),ObservationBatch(i,stamp,observations),
            ResolvedState(ResolutionStatus.RESOLVED if complete else ResolutionStatus.UNKNOWN,
                i,stamp,base_context='screen.socket' if complete else None),
            RuntimeFacts(),FrameGeometry.from_frame(f)))
    class Observer:
        def wait_until(self,predicate,**kw):
            item=frames.pop(0);assert item.sequence>kw['after_sequence'];return item
    sleeps=[];actions=Mock();inputs=[]
    actions.execute.side_effect=lambda a,g:inputs.append(g.width)
    helper=TapThroughAnimation(Observer(),actions,clock=lambda:0.,sleeper=sleeps.append)
    initial=frames.pop(0)
    result=helper.run(initial,action=object(),expected=_is_clean_socket,
        tappable=_is_tappable_animation,transient=lambda s:s.state.status is ResolutionStatus.UNKNOWN,
        policy=TapThroughPolicy(tap_interval=.2),stable_for=.25)
    assert result.succeeded and result.tap_count==2
    assert sleeps==[.2,.2] and actions.execute.call_count==2
    assert result.final_snapshot.sequence==6 and frames==[]


def test_animation_positive_cannot_override_an_upper_layer_or_foreign_base():
    from test_socket_inventory_relief import snapshot
    from dataclasses import replace
    s=snapshot(1,tappable=True)
    assert _is_tappable_animation(s)
    assert not _is_tappable_animation(replace(s,state=replace(s.state,overlays=('popup.socket_enhance_all',))))
    assert not _is_tappable_animation(snapshot(2,base='screen.socket',tappable=True))
