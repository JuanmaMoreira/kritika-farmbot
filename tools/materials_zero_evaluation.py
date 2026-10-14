"""Incremental pair-reader replay for acquired red and white Materials effects."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import cv2

from bot.ocr import RapidOcrEngine
from bot.observations import Observation, ObservationSource
from bot.perception.trading_center import row_bands
from bot.trading_row_facts import TradingRowReader
from bot.trading_materials_productive import ProductiveMaterialsAdapter
from tests.test_materials_zero_replay import ENTRIES, frame
from tests.test_materials_white_effect_replay import ENTRIES as WHITE_ENTRIES, frame as white_frame
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/materials_zero_20261011/evaluator'


class PairReplay:
    evaluation_id='trading.materials_pair'
    def __init__(self):
        self.asset_paths=(ROOT/'bot/trading_row_facts.py',ROOT/'bot/trading_materials_productive.py')
        self._reader=TradingRowReader(RapidOcrEngine())
        self._adapter=ProductiveMaterialsAdapter(None,None,self._reader,None)
        # White evidence is downscaled: native title matching is not the
        # reader under test. Replay its already-accredited geometry from log.
        self.recorded_rows={sha256(white_frame(e).tobytes()).hexdigest():e['row_top']
                            for e in WHITE_ENTRIES}
    def detect(self,image):
        pairs=[]
        for index,(top,_,_,_) in enumerate(b for b in row_bands(image) if b[3]):
            pair=self._reader.read_pair(image,top)
            if pair is not None:
                pairs.append(Observation('pair.row'+str(index),1.,ObservationSource.LOCAL_CV,value=f'{pair[0]}/{pair[1]}'))
        geometry=self._adapter.target_geometry(image)
        if geometry is not None:
            pair=self._reader.read_pair(image,geometry[0])
            if pair is not None:
                pairs.append(Observation('pair.target',1.,ObservationSource.LOCAL_CV,value=f'{pair[0]}/{pair[1]}'))
        recorded_top=self.recorded_rows.get(sha256(image.tobytes()).hexdigest())
        if recorded_top is not None:
            pair=self._reader.read_pair(image,recorded_top)
            if pair is not None:
                pairs.append(Observation('pair.recorded',1.,ObservationSource.LOCAL_CV,value=f'{pair[0]}/{pair[1]}'))
        return tuple(pairs)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    corpus=json.loads((ROOT/'datasets/trading_row_pairs_manifest.json').read_text())['entries']
    cases={e['path']:[(r['have'],r['need']) for r in e['rows']]
           for e in corpus if e['review_status']=='confirmed'}
    required={}
    for entry in ENTRIES:
        for native in (False,True):
            image=frame(entry)
            if native:image=cv2.resize(image,(2712,1224))
            path=OUT/(Path(entry['file']).stem+('_native_scale' if native else '')+'.png')
            cv2.imwrite(str(path),image)
            cases[path.relative_to(ROOT).as_posix()]=[(0,40)]
            required[path.relative_to(ROOT).as_posix()]='pair.target'
    for entry in WHITE_ENTRIES:
        path=OUT/entry['file']
        cv2.imwrite(str(path),white_frame(entry))
        cases[path.relative_to(ROOT).as_posix()]=[(entry['have'],entry['need'])]
        required[path.relative_to(ROOT).as_posix()]='pair.recorded'
    results,stats=evaluate_detector_frame_pairs(ROOT,[ROOT/p for p in cases],(PairReplay(),),cache_path=OUT/'cache.json')
    wrong=[];covered=0;unknown=0
    for result,(path,expected) in zip(results,cases.items()):
        if path in required:
            actual={0:tuple(map(int,o.value.split('/'))) for o in result.observations if o.name==required[path]}
        else:
            actual={int(o.name.split('.')[1][3:]):tuple(map(int,o.value.split('/'))) for o in result.observations if o.name.startswith('pair.row')}
        for i,pair in enumerate(expected):
            value=actual.get(i)
            if value is None:unknown+=1
            elif value!=pair:wrong.append(dict(path=path,row=i,actual=value,expected=pair))
            else:covered+=1
        if path in required and actual.get(0)!=expected[0]:
            wrong.append(dict(path=path,reason='required_pair_unreadable'))
    payload=dict(stats=asdict(stats),covered=covered,unknown=unknown,wrong=wrong)
    (OUT/'result.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload))
    return bool(wrong)


if __name__=='__main__':raise SystemExit(main())
