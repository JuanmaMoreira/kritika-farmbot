from pathlib import Path
import cv2
import pytest
from bot.craft_reader import CraftReader, CRAFT_HERO_COUNT_ROIS, parse_pair
from bot.craft_semantics import CraftFamily, CraftTier, CraftCurrency
from bot.ocr import RapidOcrEngine

ROOT = Path(__file__).parent / 'fixtures/craft_armor'

@pytest.mark.parametrize('name,quantity', [('armor_recipe', 1), ('armor_max', 2)])
def test_live_hero_helmet_selector_preserves_identity_and_economics(name, quantity):
    reader = CraftReader(RapidOcrEngine())
    recipe = reader.recipe_sample(cv2.imread(str(ROOT / (name+'.png'))), sequence=1, observed_at=1)
    assert recipe is not None
    assert (recipe.family, recipe.tier, recipe.currency) == (
        CraftFamily.ARMOR, CraftTier.HERO, CraftCurrency.MATERIAL)
    assert (recipe.unit_cost, recipe.quantity, recipe.quantity_cap) == (49, quantity, 10)
    assert reader.last_recipe_diagnostic['reads']['armor']['tier']['confidence'] >= .85

def test_live_hero_helmet_result_and_exact_material_effect():
    reader = CraftReader(RapidOcrEngine())
    result = reader.result_sample(cv2.imread(str(ROOT/'armor_result.png')), sequence=2, observed_at=2)
    assert result is not None and any('Helmet' in e for e in result.evidence)
    after = reader._read(cv2.imread(str(ROOT/'armor_result_2.png')),
                         CRAFT_HERO_COUNT_ROIS[CraftFamily.ARMOR], scale=4)
    assert after.confidence >= .85
    assert parse_pair(after.text) == (114-2*49, 999)
