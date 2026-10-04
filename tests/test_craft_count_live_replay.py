"""Real Hero Weapon count/icon frames from the failed routine investment."""
from pathlib import Path
import cv2
import pytest
from bot.craft_reader import CraftReader, CRAFT_HERO_COUNT_ROIS, parse_pair
from bot.craft_semantics import CraftFamily
from bot.ocr import RapidOcrEngine

@pytest.mark.parametrize("name", ["craft-native", "craft-stream"])
def test_post_craft_310_count_excludes_icon(name):
    frame = cv2.imread(str(Path(__file__).parent / "fixtures/craft_count" / (name + ".png")))
    result = CraftReader(RapidOcrEngine())._read(frame, CRAFT_HERO_COUNT_ROIS[CraftFamily.WEAPON], scale=4.0)
    assert result.confidence >= .85
    assert parse_pair(result.text) == (310, 999)

def test_icon_contamination_is_still_rejected():
    assert parse_pair("1310/999") is None
    assert parse_pair("1509/999") is None


def test_live_phantom_sword_result_name_excludes_item_graphic():
    frame = cv2.imread(str(Path(__file__).parent / "fixtures/craft_count/craft-result-native.png"))
    result = CraftReader(RapidOcrEngine()).result_sample(frame, sequence=12, observed_at=100)
    assert result is not None
    assert any("Phantom Sword" in evidence for evidence in result.evidence)


@pytest.mark.parametrize("name", ["native", "stream"])
def test_live_partial_max_three_recipe_keeps_full_economic_guards(name):
    frame=cv2.imread(str(Path(__file__).parent / "fixtures/craft_count" / ("craft-quantity-"+name+".png")))
    reader=CraftReader(RapidOcrEngine())
    recipe=reader.recipe_sample(frame,sequence=15,observed_at=100)
    assert recipe is not None
    assert recipe.family is CraftFamily.WEAPON
    assert recipe.quantity==3 and recipe.quantity_cap==10 and recipe.unit_cost==49
    assert reader.last_recipe_diagnostic['reads']['quantity']['confidence']>=.85
