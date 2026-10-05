"""Final Keys trade can produce a red zero; never infer it from consumption."""
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from bot.ocr import RapidOcrEngine
from bot.trading_key_row_reader import read_key_samples

ROOT = Path(__file__).parent/'fixtures/keys_zero'

@pytest.fixture(scope='module')
def reader():
    return SimpleNamespace(engine=RapidOcrEngine())

@pytest.mark.parametrize('index',range(3))
def test_real_stream_zero_and_other_balance_are_read_exactly(reader,index):
    entry=json.loads((ROOT/'manifest.json').read_text())[str(index)]
    frame=np.zeros(entry['shape'],dtype=np.uint8)
    h,w=frame.shape[:2];x1,y1,x2,y2=entry['roi']
    frame[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(ROOT/f'stream_{index}.png'))
    diagnostics={'silver_key':[],'gold_key':[]}
    samples=read_key_samples(reader,frame,index+1,diagnostics)
    assert (samples['silver_key'].have,samples['silver_key'].need)==(0,10)
    assert (samples['gold_key'].have,samples['gold_key'].need)==(340,10)
    assert diagnostics['silver_key'][0]['pair_reads'][0]['confidence']>=.90
