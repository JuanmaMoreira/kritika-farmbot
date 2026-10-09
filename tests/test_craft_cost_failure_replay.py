"""Native regression: Armor selector cost 49 rejected through icon clutter."""
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from bot.craft_reader import CraftReader, CRAFT_COST_ROI
from bot.craft_semantics import CraftFamily, CraftCurrency
from bot.ocr import RapidOcrEngine

FIXTURE=Path(__file__).parent/'fixtures/craft_cost_failure'

def native_panel():
    manifest=json.loads((FIXTURE/'manifest.json').read_text())
    h,w=manifest['shape'];image=np.zeros((h,w,3),np.uint8)
    for name,(x1,y1,x2,y2) in manifest['boxes'].items():
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(FIXTURE/(name+'.png')))
    return image

@pytest.fixture(scope='module')
def reader():return CraftReader(RapidOcrEngine())

def test_native_icon_crop_reproduces_old_denial_and_digits_crop_restores_authority(reader):
    image=native_panel()
    old=reader._read(image,(.480,.570,.550,.680),scale=4.)
    assert old.text=='49' and old.confidence<.80
    new=reader._read(image,CRAFT_COST_ROI,scale=4.)
    assert new.text=='49' and new.confidence>=.80
    recipe=reader.recipe_sample(image,sequence=7,observed_at=10.)
    assert recipe is not None and recipe.family is CraftFamily.ARMOR
    assert recipe.unit_cost==49 and recipe.currency is CraftCurrency.MATERIAL
    assert recipe.quantity==1 and recipe.quantity_cap==10

def test_missing_cost_never_authorizes_material_confirmation(reader):
    image=native_panel();h,w=image.shape[:2];x1,y1,x2,y2=CRAFT_COST_ROI
    image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=0
    assert reader.recipe_sample(image,sequence=8,observed_at=10.) is None
