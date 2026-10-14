"""Fresh Sapphire precheck after rewarded ad, failure 7ac67227."""
from types import SimpleNamespace as S
from unittest.mock import Mock
import json
from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.catalog import BASE_CONTEXT_RULES, OVERLAY_RULES, build_default_resolver
from bot.arena_semantics import ARENA_OBSERVATIONS
from bot.fact_reader import RuntimeFactReader
from bot.flow_contracts import FlowStatus
from bot.flow_registry import _build_monster_wave
from bot.observations import Observation, ObservationSource
from bot.ocr import OcrResult
from bot.ocr_extractors import build_sapphires_extractor
from bot.perception import (
    MONSTER_WAVE_ENTRY_READINESS_SCOPE, build_default_perception, select_detectors,
)
from bot.runtime_observer import RuntimeObserver


def test_scope_preserves_all_context_and_blocker_dependencies():
    full=build_default_perception()
    scoped=select_detectors(full,MONSTER_WAVE_ENTRY_READINESS_SCOPE)
    names={getattr(getattr(d,'spec',None),'name',None) for d in scoped.detectors}
    specialized={
        'landmark.meteorites_main','landmark.meteorites_detail','activity.meteorites_loading',
        'indicator.daily_quests_progress_reward_claimable',
        'indicator.guild_attendance_active','indicator.guild_attendance_completed',
        'indicator.pet_epic_available','indicator.pet_epic_unavailable',
        'landmark.combine_context','landmark.pet_combine_result',
        'landmark.pet_mass_evolve_confirmation',
    }
    specialized.update(ARENA_OBSERVATIONS)
    required={name for rule in (*BASE_CONTEXT_RULES,*OVERLAY_RULES) for name in rule.requires}
    assert required<=names|specialized
    assert any(type(d).__name__=='ArenaDetector' for d in scoped.detectors)
    assert any(type(d).__name__=='StagesDetector' for d in scoped.detectors)
    assert all(d in full.detectors for d in scoped.detectors)


def runtime(monkeypatch,*,value=338,visible=(),cancel=False,slow_retained=False,
            confidence=.99962):
    # Recorded snapshot context plus logged analysis/OCR/capture-age budget.
    captured=json.loads((Path(__file__).parent/'fixtures/mw_readiness/lobby.json').read_text())
    now=[100.]
    sequence=[3735]
    cancelled=[False]
    calls=[]
    image=np.zeros((100,200,3),np.uint8)
    class Source:
        def get_frame(self):
            sequence[0]+=21
            return FrameSnapshot(image,now[0]-.1848,sequence[0])
    perception=build_default_perception()
    for detector in perception.detectors:
        name=getattr(getattr(detector,'spec',None),'name',None)
        kind=type(detector).__name__
        def detect(frame,name=name,kind=kind):
            calls.append(kind)
            if name=='landmark.lobby_trading_center_label':now[0]+=1.8940432 if slow_retained else 1.3
            if kind=='PetLowTierCandidateDetector':now[0]+=.5940432
            names={o['name'] for o in captured['observations']}|set(visible)
            if kind=='StagesDetector' and 'stages.base' in names:
                return (Observation('stages.base',1.,ObservationSource.LOCAL_CV),)
            return (Observation(name,1.,ObservationSource.LOCAL_CV),) if name in names else ()
        monkeypatch.setattr(detector,'detect',detect)
    observer=RuntimeObserver(Source(),perception,build_default_resolver(),
        clock=lambda:now[0],sleeper=lambda t:now.__setitem__(0,now[0]+t))
    class Engine:
        def recognize(self,image):
            now[0]+=.0907
            if cancel:cancelled[0]=True
            return OcrResult(str(value)+'/102',confidence)
    facts=RuntimeFactReader(observer,(build_sapphires_extractor(Engine()),),clock=lambda:now[0])
    deps=S(observer=observer,actions=ActionExecutor(Mock()),facts=facts,events=None,
           cancel_requested=lambda:cancelled[0])
    # Exercise the real bare factory, also used by productive MW, without
    # constructing unrelated economic owners or loading an OCR model.
    monkeypatch.setattr('bot.flow_registry._build_productive_monster_wave',lambda d,t,b:b())
    flow=_build_monster_wave(deps)
    flow.activity.clock=lambda:now[0]
    return flow,calls,facts


def test_logged_latency_old_fails_fixed_confirms_fresh_338(monkeypatch):
    flow,calls,facts=runtime(monkeypatch)
    readiness=flow.readiness_observer
    assert readiness.source is flow.activity.observer.source
    assert readiness.resolver is flow.activity.observer.resolver
    flow.readiness_observer=None
    old=flow.entry_readiness(pressure_relief=True)
    assert old.status is FlowStatus.FAILED and old.error=='fresh Lobby sapphires unavailable'
    calls.clear()
    flow.readiness_observer=readiness
    assert flow.entry_readiness(pressure_relief=True) is None
    assert 'PetLowTierCandidateDetector' not in calls
    assert facts.observer is flow.activity.observer  # no shared observer mutation
    assert flow.activity.actions.adb.mock_calls==[]


@pytest.mark.parametrize('value',[0,101])
def test_pressure_no_work_still_requires_fresh_consensus(monkeypatch,value):
    flow,_,_=runtime(monkeypatch,value=value)
    assert flow.entry_readiness(pressure_relief=True).event_count('monster_wave.no_work')==1


@pytest.mark.parametrize('visible',[
    ('landmark.mailbox_title',),('landmark.character_select_header',),
    ('stages.base',),
])
def test_foreign_or_ambiguous_context_fails_readiness(monkeypatch,visible):
    flow,_,_=runtime(monkeypatch,visible=visible)
    assert flow.entry_readiness(pressure_relief=True).status is FlowStatus.FAILED


@pytest.mark.parametrize('landmark,overlay',[
    ('landmark.quick_menu_lobby_tile','menu.quick'),
    ('landmark.equipment_inventory_full_prompt','popup.equipment_inventory_full'),
])
def test_scope_keeps_covered_lobby_evidence_for_navigation_owner(monkeypatch,landmark,overlay):
    flow,_,_=runtime(monkeypatch,visible=(landmark,))
    full=flow.activity.observer.observe().state
    scoped=flow.readiness_observer.observe().state
    assert overlay in full.overlays and scoped.overlays==full.overlays
    assert scoped.base_context==full.base_context
    assert flow.activity.actions.adb.mock_calls==[]


def test_cancellation_during_ocr_stops_readiness(monkeypatch):
    flow,_,_=runtime(monkeypatch,cancel=True)
    assert flow.entry_readiness().status is FlowStatus.CANCELLED


def test_slow_scoped_frame_still_fails_the_unchanged_age_guard(monkeypatch):
    flow,_,_=runtime(monkeypatch,slow_retained=True)
    assert flow.entry_readiness().status is FlowStatus.FAILED


@pytest.mark.parametrize('value,confidence', [('?', .99962), (338, .49)])
def test_unreadable_or_low_confidence_is_failure_never_no_resource(monkeypatch,value,confidence):
    flow,_,_=runtime(monkeypatch,value=value,confidence=confidence)
    result=flow.entry_readiness(pressure_relief=True)
    assert result.status is FlowStatus.FAILED
    assert result.event_count('monster_wave.no_work')==0
    assert flow.activity.actions.adb.mock_calls==[]


@pytest.mark.parametrize('value', [100,101,102])
def test_arena_one_pass_readiness_keeps_non_pressure_policy(monkeypatch,value):
    flow,_,_=runtime(monkeypatch,value=value)
    assert flow.entry_readiness(pressure_relief=False) is None
    assert flow.activity.actions.adb.mock_calls==[]


def test_explicit_fact_observer_does_not_leak_to_default_consumers():
    from tests.test_fact_reader import reader
    default=reader([1,2], ['5','5'])
    selected=reader([11,12], ['unused','unused']).observer
    result=default.read_sapphires(after_sequence=10,timeout=3,observer=selected)
    assert result.fact.value==5 and result.fact.sequence==12
    assert default.observer is not selected
    default._extractors['resource.sapphires'].engine.texts=['7','7']
    result=default.read_sapphires(after_sequence=0,timeout=3)
    assert result.fact.value==7 and result.fact.sequence==2
