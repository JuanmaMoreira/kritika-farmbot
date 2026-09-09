"""MW HUD evidence and explicit context selection; default Lobby/WB stays intact."""
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE, POPUP_MW_WEEKLY
from bot.observations import ObservationBatch
from bot.ocr import RapidOcrEngine, OcrResult, OcrEngineError
from bot.ocr_extractors import (build_monster_wave_sapphires_extractor,
                                ExtractionStatus, SAPPHIRES_ROI)
from bot.runtime import build_runtime_fact_reader
from bot.runtime_facts import FactReadStatus, FactQuality
from bot.runtime_observer import RuntimeSnapshot, RuntimeFacts, RuntimeObserver
from bot.state import ResolutionStatus, ResolvedState
from test_world_boss_flow import snapshot


ROOT=Path(__file__).resolve().parents[1]


def test_mw_ocr_replays_curated_positives_and_rejects_contextual_negatives():
    payload=json.loads((ROOT/'datasets/monster_wave_ocr_manifest.json').read_text())
    entries=payload['entries']
    assert {e['expected_value'] for e in entries if e['expected_value'] is not None}=={0,70,83,183}
    if not all((ROOT/e['path']).is_file() for e in entries):
        pytest.skip('local MW OCR evidence corpus is not present')
    engine=Mock(wraps=RapidOcrEngine())
    extractor=build_monster_wave_sapphires_extractor(engine)
    assert list(extractor.region)==payload['curation']['roi']
    assert extractor.region!=SAPPHIRES_ROI
    for sequence,e in enumerate(entries,1):
        frame=cv2.imread(str(ROOT/e['path']));before=engine.recognize.call_count
        state=ResolvedState(ResolutionStatus.UNKNOWN if e['base_context']=='unknown' else ResolutionStatus.RESOLVED,
                            sequence,float(sequence),
                            base_context=None if e['base_context']=='unknown' else e['base_context'],
                            overlays=tuple(e['overlays']))
        s=RuntimeSnapshot(FrameSnapshot(frame,float(sequence),sequence),
                          ObservationBatch(sequence,float(sequence)),state,RuntimeFacts(),
                          FrameGeometry.from_frame(frame))
        result=extractor.extract(s)
        assert result.status.value==e['expected_status'],e['path']
        assert result.value==e['expected_value'],e['path']
        assert engine.recognize.call_count-before==int(e['expected_value'] is not None)


@pytest.mark.parametrize('status',[ResolutionStatus.UNKNOWN,ResolutionStatus.AMBIGUOUS])
def test_unresolved_mw_hud_never_invokes_ocr(status):
    engine=Mock();s=snapshot(1,status=status)
    assert build_monster_wave_sapphires_extractor(engine).extract(s).status is ExtractionStatus.CONTEXT_MISMATCH
    engine.recognize.assert_not_called()


@pytest.mark.parametrize('context,overlays',[(SCREEN_LOBBY,()),(SCREEN_MONSTER_WAVE,(POPUP_MW_WEEKLY,)),
                                           (SCREEN_MONSTER_WAVE,('popup.unacquired',))])
def test_wrong_or_obstructed_context_never_invokes_ocr(context,overlays):
    engine=Mock();s=snapshot(1,base=context,overlays=overlays)
    assert build_monster_wave_sapphires_extractor(engine).extract(s).status is ExtractionStatus.CONTEXT_MISMATCH
    engine.recognize.assert_not_called()


@pytest.mark.parametrize('texts,value,status',[
    (['3','3'],3,FactReadStatus.CONFIRMED),
    (['4','4'],4,FactReadStatus.CONFIRMED),
    (['8','3','3'],3,FactReadStatus.CONFIRMED),
    (['1','2','3'],None,FactReadStatus.UNCERTAIN),
    (['bad','bad','bad'],None,FactReadStatus.UNREADABLE),
    ([OcrEngineError('failed')],None,FactReadStatus.FAILURE),
])
def test_runtime_mw_reader_requires_bounded_fresh_consensus(texts,value,status):
    observer=Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect=[snapshot(i,base=SCREEN_MONSTER_WAVE) for i in range(11,14)]
    engine=Mock()
    engine.recognize.side_effect=[t if isinstance(t,Exception) else OcrResult(t,.99) for t in texts]
    reader=build_runtime_fact_reader(observer,ocr_engine=engine)
    result=reader.read_sapphires(context=SCREEN_MONSTER_WAVE,after_sequence=10,timeout=6)
    assert result.status is status
    assert observer.wait_until.call_count<=3
    cursors=[c.kwargs['after_sequence'] for c in observer.wait_until.call_args_list]
    assert cursors==list(range(10,10+len(cursors)))
    if value is not None:
        assert result.fact.value==value and result.fact.context==SCREEN_MONSTER_WAVE
        assert result.fact.quality is FactQuality.CONSENSUS
        assert len(result.fact.evidence)==2 and min(e.sequence for e in result.fact.evidence)>10


def test_explicit_mw_context_cannot_fall_back_to_lobby_roi():
    observer=Mock(spec=RuntimeObserver)
    observer.wait_until.return_value=snapshot(11,base=SCREEN_LOBBY)
    engine=Mock()
    result=build_runtime_fact_reader(observer,ocr_engine=engine).read_sapphires(
        context=SCREEN_MONSTER_WAVE,after_sequence=10,timeout=6)
    assert result.status is FactReadStatus.CONTEXT_MISMATCH
    engine.recognize.assert_not_called()


def test_default_sapphires_consumer_preserves_lobby_contract_and_consensus():
    observer=Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect=[snapshot(11,base=SCREEN_LOBBY),snapshot(12,base=SCREEN_LOBBY)]
    engine=Mock();engine.recognize.return_value=OcrResult('8/66',.99)
    result=build_runtime_fact_reader(observer,ocr_engine=engine).read_sapphires(after_sequence=10,timeout=6)
    assert result.status is FactReadStatus.CONFIRMED and result.fact.value==8
    assert result.fact.context==SCREEN_LOBBY


def test_default_sapphires_consumer_still_rejects_mw_context():
    observer=Mock(spec=RuntimeObserver)
    observer.wait_until.return_value=snapshot(11,base=SCREEN_MONSTER_WAVE)
    engine=Mock()
    result=build_runtime_fact_reader(observer,ocr_engine=engine).read_sapphires(after_sequence=10,timeout=6)
    assert result.status is FactReadStatus.CONTEXT_MISMATCH
    engine.recognize.assert_not_called()
