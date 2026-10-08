"""Causal Sell binding: arbitrary OCR names do not authorize or deny Bulk."""

from dataclasses import replace
import time
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.equipment_sell_operation import EquipmentSellCandidate, EquipmentSellRequest
from bot.equipment_sell_policy import EquipmentSellPolicy, confirmation_matches_item
from bot.equipment_sell_reader import parse_confirmation, parse_item_detail
from bot.equipment_sell_runtime import EquipmentSellRuntime
from bot.equipment_sell_semantics import (
    CONFIGURABLE_EQUIPMENT_TYPES,
    EquipmentBulkGroup as B,
    EquipmentGrade as G,
    EquipmentItemFact,
    EquipmentInventoryFact,
    EquipmentSellConfirmationFact,
    EquipmentType as T,
)
from bot.semantic_actions import CloseEquipmentDetail


def sale(*, grade=G.LEGENDARY, kind=T.HELMET, enhance=False,
         name="Unseen item name", popup_name="Different OCR transcription", tier_by_color=False):
    adb = Mock()
    group = B.ENHANCE_GRADE if enhance else B.TYPE_GRADE if grade is G.ETHEREAL else B.EQUIPMENT_GRADE

    class Source:
        sequence = 0

        def get_frame(self):
            self.sequence += 1
            return FrameSnapshot(np.zeros((200, 400, 3), np.uint8), time.monotonic(), self.sequence)

    class Reader:
        def inventory_sample(self, frame, *, sequence, observed_at):
            return EquipmentInventoryFact(135 if adb.tap.call_count < 3 else 134, 128, 8, 22,
                                          sequence, observed_at, (sequence,))

        def detail_sample(self, frame, *, sequence, observed_at):
            return EquipmentItemFact(name, grade, kind, enhance, sequence, observed_at,
                                     (sequence,), sell_available=True, grade_visual=grade,
                                     tier_by_color=tier_by_color)

        def confirmation_sample(self, frame, *, sequence, observed_at):
            return EquipmentSellConfirmationFact(popup_name, group,
                                                 kind if group is B.TYPE_GRADE else None,
                                                 sequence, observed_at, (sequence,))

    reader = Reader()
    runtime = EquipmentSellRuntime(Source(), reader, ActionExecutor(adb), sample_interval=0,
                                   sample_timeout=.1)
    expected = reader.detail_sample(None, sequence=2, observed_at=time.monotonic())
    expected = replace(expected, sample_sequences=(1, 2))
    authorization = EquipmentSellPolicy(frozenset(CONFIGURABLE_EQUIPMENT_TYPES), True).authorize(expected)
    request = EquipmentSellRequest(authorization, EquipmentSellCandidate(8, 15))
    return runtime, reader, adb, request


def test_latest_failed_ocr_pair_uses_verified_origin_and_confirms_only_once():
    # Native diagnostics: fd48d8bf events 2112/2113 and 2120/2121,
    # 2026-10-07. The popup OCR loses a 't' with confidence .99925/.99922.
    # Post-sale Item Count is simulated: the historical run cancelled before sale.
    name, grade, kind, enhance = parse_item_detail("Laoku's Destructive Gear", "[Legendary] Helmet")
    popup_name, group, group_type = parse_confirmation(
        "Selling [Laoku's Desructive Gear] for 10 K",
        ["If you would like to sell all of the", "Equipment of this grade,", "use the Sell [Bulk] button."],
    )
    assert group is B.EQUIPMENT_GRADE and group_type is None
    runtime, _, adb, request = sale(grade=grade, kind=kind, enhance=enhance,
                                  name=name, popup_name=popup_name)
    result = runtime.execute(request)
    assert result.succeeded and result.confirm_count == 1 and adb.tap.call_count == 3
    assert result.confirmation.source_item_sequence == result.item.sequence
    assert not confirmation_matches_item(replace(result.confirmation, source_item_sequence=None), result.item)


def test_color_tier_without_selected_name_keeps_causal_popup_binding_and_count_effect():
    runtime, _, adb, request = sale(name="", tier_by_color=True,
                                  popup_name="Laoku's Desructive Gear")
    result = runtime.execute(request)
    assert result.succeeded and result.item.grade is G.LEGENDARY
    assert result.item.name == "" and result.item.tier_by_color
    assert result.confirmation.source_item_sequence == result.item.sequence
    assert result.confirm_count == 1 and adb.tap.call_count == 3
    assert result.after.item_count < result.before.item_count


@pytest.mark.parametrize("kind", sorted(CONFIGURABLE_EQUIPMENT_TYPES, key=lambda value: value.value))
@pytest.mark.parametrize("grade,enhance", [(G.RARE, False), (G.ETHEREAL, False), (G.ETHEREAL, True)])
def test_all_types_and_bulk_families_use_origin_instead_of_arbitrary_name(kind, grade, enhance):
    runtime, _, adb, request = sale(grade=grade, kind=kind, enhance=enhance)
    result = runtime.execute(request)
    assert result.succeeded and result.confirm_count == 1 and adb.tap.call_count == 3
    assert result.confirmation.item_name != result.item.name
    assert result.confirmation.source_item_sequence == result.item.sequence


@pytest.mark.parametrize("damage", ["unknown", "family", "type", "contradictory"])
def test_causal_origin_does_not_replace_positive_authorized_bulk_scope(damage):
    runtime, reader, adb, request = sale(grade=G.ETHEREAL)
    original = reader.confirmation_sample

    def confirmation(frame, **kwargs):
        fact = original(frame, **kwargs)
        if damage == "unknown": return None
        if damage == "family": return replace(fact, group=B.ENHANCE_GRADE, group_type=None)
        if damage == "type": return replace(fact, group_type=T.BOOTS)
        return replace(fact, contradictory=True)

    reader.confirmation_sample = confirmation
    result = runtime.execute(request)
    assert not result.succeeded and result.confirm_count == 0
    assert adb.tap.call_count == 3  # Select, open, cancel.


def test_popup_from_other_verified_panel_denied_even_when_names_match():
    runtime, _, _, request = sale(popup_name="Unseen item name")
    result = runtime.execute(request)
    popup = replace(result.confirmation, source_item_sequence=result.item.sequence - 1)
    assert not confirmation_matches_item(popup, result.item)
    assert not request.authorization.allows_bulk(result.item, popup)


@pytest.mark.parametrize("damage", ["input", "barrier", "pre_open_sample", "stale", "unconfirmed"])
def test_lost_origin_cannot_fall_back_to_matching_ocr_name(damage):
    runtime, _, adb, request = sale(popup_name="Unseen item name")
    original = runtime._read_next

    def read(method, predicate=lambda value: True):
        fact = original(method, predicate)
        if method == "confirmation_sample":
            if damage == "input": runtime._tap(CloseEquipmentDetail())
            elif damage == "barrier": runtime._not_before += 1
            elif damage == "pre_open_sample":
                fact = replace(fact, sample_sequences=(runtime._sale_origin[1], fact.sequence))
            elif damage == "unconfirmed": fact = replace(fact, sample_sequences=(fact.sequence,))
            else: fact = replace(fact, observed_at=time.monotonic() - 3)
        return fact

    runtime._read_next = read
    result = runtime.execute(request)
    assert result.reason == "confirmation_unreadable_or_stale" and result.confirm_count == 0
    assert adb.tap.call_count == (4 if damage == "input" else 3)


def test_origin_does_not_allow_retry_when_post_sale_count_is_inconclusive():
    runtime, reader, adb, request = sale()
    original = reader.inventory_sample
    reader.inventory_sample = lambda frame, **kwargs: replace(original(frame, **kwargs), item_count=135)
    result = runtime.execute(request)
    assert not result.succeeded and result.confirm_count == 1 and adb.tap.call_count == 3
    assert result.reason == "post_item_count_unreadable_or_stale"
