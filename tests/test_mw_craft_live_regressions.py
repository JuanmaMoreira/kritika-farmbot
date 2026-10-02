from pathlib import Path
import cv2
from bot.ocr import RapidOcrEngine
from bot.craft_reader import CraftReader
from bot.equipment_sell_reader import EquipmentSellReader
ROOT=Path(__file__).resolve().parents[1]


def test_native_craft_quick_menu_guild_excludes_icon_noise():
    frame=cv2.imread(str(ROOT/'artifacts/mw_stabilization/craft_menu_native.png'))
    reader=CraftReader(RapidOcrEngine())
    fact=reader.quick_menu_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.complete
    assert reader.last_quick_menu_diagnostic['guild']['text']=='Guild'
    assert reader.last_quick_menu_diagnostic['guild']['confidence']>=.90
    assert reader.context_sample(frame,sequence=1,observed_at=1.) is None


def test_native_craft_capacity_accepts_dynamic_124_capacity():
    frame=cv2.imread(str(ROOT/'artifacts/mw_stabilization/equipment_capacity_native.png'))
    reader=EquipmentSellReader(RapidOcrEngine())
    fact=reader.inventory_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None
    assert (fact.item_count,fact.capacity,fact.page,fact.total_pages)==(107,124,1,22)
    assert reader.last_context_diagnostic['count']['parsed']==(107,124)


def test_native_hero_recipe_currency_crop_excludes_icon_and_cost():
    frame=cv2.imread(str(ROOT/'artifacts/mw_stabilization/craft_recipe_open_native.png'))
    reader=CraftReader(RapidOcrEngine())
    fact=reader.recipe_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None
    assert (fact.family.value,fact.tier.value,fact.currency.value)==('weapon','hero','material')
    assert (fact.unit_cost,fact.quantity,fact.quantity_cap)==(49,1,10)
    currency=reader.last_recipe_diagnostic['reads']['currency']
    assert currency['text']=='Material to be used:'
    assert currency['confidence']>=.99


def test_native_craft_animation_is_rejected_and_stable_result_is_readable():
    reader=CraftReader(RapidOcrEngine())
    animation=cv2.imread(str(ROOT/'artifacts/mw_stabilization/craft_result_native_40.png'))
    stable=cv2.imread(str(ROOT/'artifacts/mw_stabilization/craft_result_stable_native.png'))
    assert reader.result_sample(animation,sequence=1,observed_at=1.) is None
    fact=reader.result_sample(stable,sequence=2,observed_at=2.)
    assert fact is not None and fact.marker=='craft_result'


def test_native_draken10_weapon_cost_crop_remains_verified():
    frame=cv2.imread(str(ROOT/'artifacts/mw_stabilization/craft_no_effect_native.png'))
    reader=CraftReader(RapidOcrEngine())
    fact=reader.context_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.weapon_hero_cost==49
    assert fact.weapon_material==420
    assert reader.last_context_diagnostic['reads']['weapon_cost']['confidence']>=.99
