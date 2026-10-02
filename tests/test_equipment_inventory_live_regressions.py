from pathlib import Path
import cv2
import pytest
from bot.equipment_sell_reader import EquipmentSellReader
from bot.ocr import RapidOcrEngine
ROOT=Path(__file__).resolve().parents[1]/"artifacts/mw_stabilization"

@pytest.fixture(scope="module")
def reader():
    return EquipmentSellReader(RapidOcrEngine())

@pytest.mark.parametrize("file,grade,kind,enhance",[
 ("equipment_detail_p8_s15.png","rare","helmet",False),
 ("equipment_detail_p8_s14.png","epic","chest",True),
 ("equipment_detail_p8_s12.png","epic","chest",False),
 ("equipment_detail_p8_s0.png","legendary","weapon",False),
 ("equipment_detail_p5_s15.png","ethereal","necklace",False),
 ("equipment_detail_p1_s15.png","ethereal+","chest",False),
])
def test_native_tail_panel_redundant_grade_and_sell_guards(reader,file,grade,kind,enhance):
    frame=cv2.imread(str(ROOT/file));assert frame is not None
    fact=reader.detail_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.complete
    assert (fact.grade.value,fact.equipment_type.value,fact.enhance) == (grade,kind,enhance)
    if grade != "ethereal+":
        assert fact.grade_visual is fact.grade and fact.sell_available is True


def test_native_capacity_purchase_modal_cannot_be_mistaken_for_inventory(reader):
    frame=cv2.imread(str(ROOT/"equipment_expansion_popup.png"));assert frame is not None
    assert reader.expansion_visible(frame)
    assert reader.expansion_sample(frame,sequence=7,observed_at=7.) == (180,7,7.)
    assert reader.inventory_sample(frame,sequence=7,observed_at=7.) is None
    grid=cv2.imread(str(ROOT/"equipment_next_row.png"));assert grid is not None
    assert reader.capacity_row_cost(grid,0) == 180
    assert not reader.expansion_visible(grid)
    assert reader.expansion_sample(grid,sequence=8,observed_at=8.) is None


def test_native_rare_bulk_identity_and_family(reader):
    frame=cv2.imread(str(ROOT/"equipment_rare_popup.png"));assert frame is not None
    fact=reader.confirmation_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.complete
    assert fact.item_name == "Laoku's Mighty Gear"
    assert fact.group.value == "equipment_grade" and fact.group_type is None


def test_native_ethereal_bulk_popup_wrap_preserves_exact_type(reader):
    from bot.equipment_sell_semantics import EquipmentBulkGroup,EquipmentType
    frame=cv2.imread(str(ROOT/"equipment_ethereal_boots_popup.png"))
    assert frame is not None
    fact=reader.confirmation_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.complete
    assert fact.item_name == "Laoku's Awakened Boots"
    assert fact.group is EquipmentBulkGroup.TYPE_GRADE
    assert fact.group_type is EquipmentType.BOOTS


def test_native_ethereal_chest_type_wrap_and_currency_initial(reader):
    from bot.equipment_sell_semantics import EquipmentBulkGroup,EquipmentType
    frame=cv2.imread(str(ROOT/"equipment_ethereal_chest_popup.png"))
    assert frame is not None
    fact=reader.confirmation_sample(frame,sequence=1,observed_at=1.)
    assert fact is not None and fact.complete
    assert fact.item_name == "Laoku's Awakened Tunic"
    assert fact.group is EquipmentBulkGroup.TYPE_GRADE
    assert fact.group_type is EquipmentType.CHEST
