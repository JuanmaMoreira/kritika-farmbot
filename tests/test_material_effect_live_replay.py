"""Post-MAX 840 -> 40: disconnected leading 4 must not become 1."""
from pathlib import Path
import cv2
import pytest
from bot.ocr import RapidOcrEngine
from bot.trading_row_facts import TradingRowReader

@pytest.mark.parametrize("name", ["native", "stream"])
def test_material_effect_40_pair_survives_independent_margin_read(name):
    frame=cv2.imread(str(Path(__file__).parent / "fixtures/material_effect" / (name+".png")))
    diagnostic={}
    pair=TradingRowReader(RapidOcrEngine()).read_pair(frame,.7288614379084968,diagnostics=diagnostic)
    assert pair==(40,40)
    assert len(diagnostic["pair_reads"])==2
    assert all(read["parse_result"]==(40,40) for read in diagnostic["pair_reads"])
