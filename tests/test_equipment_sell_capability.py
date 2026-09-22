"""Standalone Equipment Sell semantics, policy and bounded operation."""

from pathlib import Path

import pytest

from bot.equipment_sell_operation import (
    EquipmentSellCandidate,
    EquipmentSellOutcome,
    EquipmentSellRequest,
    execute_equipment_sell,
)
from bot.equipment_sell_policy import EquipmentSellAuthorization
from bot.equipment_sell_reader import (
    parse_confirmation,
    parse_item_count,
    parse_item_detail,
    parse_page,
)
from bot.equipment_sell_semantics import (
    CONFIGURABLE_EQUIPMENT_TYPES,
    DISPOSABLE_GRADES,
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentInventoryFact,
    EquipmentItemFact,
    EquipmentSellConfirmationFact,
    EquipmentType,
    PROTECTED_ACCESSORY_TYPES,
    consensus_facts,
)


def _inventory(count=120, capacity=112, page=7, total=22, sequence=2, *, confirmed=True):
    return EquipmentInventoryFact(
        count,
        capacity,
        page,
        total,
        sequence,
        float(sequence),
        (sequence - 1, sequence) if confirmed else (sequence,),
        (f"count:{count}/{capacity}", f"page:{page}/{total}"),
    )


def _item(
    *,
    name="Gloves (Enhance)",
    grade=EquipmentGrade.EPIC,
    equipment_type=EquipmentType.GLOVES,
    enhance=True,
    sequence=4,
    confirmed=True,
    contradictory=False,
):
    return EquipmentItemFact(
        name,
        grade,
        equipment_type,
        enhance,
        sequence,
        float(sequence),
        (sequence - 1, sequence) if confirmed else (sequence,),
        ("detail",),
        contradictory,
    )


def _confirmation(
    *,
    name="Gloves (Enhance)",
    group=EquipmentBulkGroup.ENHANCE_GRADE,
    group_type=None,
    sequence=8,
    confirmed=True,
    contradictory=False,
):
    return EquipmentSellConfirmationFact(
        name,
        group,
        group_type,
        sequence,
        float(sequence),
        (sequence - 1, sequence) if confirmed else (sequence,),
        ("popup",),
        contradictory,
    )


def _authorization(**overrides):
    values = {
        "allowed_types": frozenset({EquipmentType.GLOVES}),
        "allowed_grades": frozenset({EquipmentGrade.EPIC}),
        "allowed_enhance_states": frozenset({True}),
        "allowed_bulk_groups": frozenset({EquipmentBulkGroup.ENHANCE_GRADE}),
        "label": "test",
    }
    values.update(overrides)
    return EquipmentSellAuthorization(**values)


def _request(**overrides):
    values = {
        "authorization": _authorization(),
        "candidate": EquipmentSellCandidate(7, 15),
    }
    values.update(overrides)
    return EquipmentSellRequest(**values)


class _Script:
    def __init__(self, details=None, confirmations=None, inventories=None):
        self.details = list(details or [_item(sequence=4), _item(sequence=6)])
        self.confirmations = list(confirmations or [_confirmation(sequence=8)])
        self.inventories = list(inventories or [_inventory(count=119, sequence=10)])
        self.inputs = []

    def select(self, candidate):
        self.inputs.append(("select", candidate))

    def read_detail(self):
        return self.details.pop(0) if self.details else None

    def open_confirmation(self):
        self.inputs.append(("open", None))

    def read_confirmation(self):
        return self.confirmations.pop(0) if self.confirmations else None

    def confirm_bulk(self):
        self.inputs.append(("confirm_bulk", None))

    def cancel(self):
        self.inputs.append(("cancel", None))

    def read_inventory(self):
        return self.inventories.pop(0) if self.inventories else None


def _execute(script, *, request=None, before=None, cancel=lambda: False):
    return execute_equipment_sell(
        request=request or _request(),
        before=before or _inventory(),
        select_candidate=script.select,
        read_detail=script.read_detail,
        open_confirmation=script.open_confirmation,
        read_confirmation=script.read_confirmation,
        confirm_bulk=script.confirm_bulk,
        cancel_confirmation=script.cancel,
        read_inventory=script.read_inventory,
        cancel_requested=cancel,
    )


# Exact accepted vocabulary and strict parsers.


def test_exact_six_configurable_types_and_three_protected_accessories():
    assert {value.value for value in CONFIGURABLE_EQUIPMENT_TYPES} == {
        "weapon", "helmet", "chest", "pants", "gloves", "boots"
    }
    assert {value.value for value in PROTECTED_ACCESSORY_TYPES} == {
        "earring", "necklace", "ring"
    }


@pytest.mark.parametrize(
    "text,expected",
    [("※ Item Count : 120 / 112", (120, 112)), ("Item Count: 1,200/352", (1200, 352))],
)
def test_item_count_parser_requires_contextual_label(text, expected):
    assert parse_item_count(text) == expected


@pytest.mark.parametrize("text", ["120/112", "Item Count: ?/112", "Item Count: 120/0"])
def test_item_count_parser_fails_closed(text):
    assert parse_item_count(text) is None


def test_page_and_current_detail_parser():
    assert parse_page("7 / 22") == (7, 22)
    assert parse_item_detail("Gloves (Enhance)", "[Epic] Gloves") == (
        "Gloves (Enhance)", EquipmentGrade.EPIC, EquipmentType.GLOVES, True
    )


@pytest.mark.parametrize(
    "title,line",
    [
        ("Gloves (Enhanc)", "[Epic] Gloves"),
        ("Gloves", "[Ethereal++] Gloves"),
        ("Gloves", "[Epic] Unknown"),
        ("", "[Epic] Gloves"),
    ],
)
def test_detail_parser_rejects_unknown_or_contradictory_text(title, line):
    assert parse_item_detail(title, line) is None


def test_current_confirmation_parser_proves_identity_and_enhance_group():
    assert parse_confirmation(
        "Selling [Gloves (Enhance)].",
        (
            "If you want to sell all of the (Enhance)",
            "items of the same grade,",
            "please tap the Sell (Bulk) button below.",
        ),
    ) == ("Gloves (Enhance)", EquipmentBulkGroup.ENHANCE_GRADE, None)


def test_current_confirmation_parser_accepts_equipment_grade_bracket_variant():
    assert parse_confirmation(
        "Selling [Laoku's Fatal Armor].",
        (
            "If you would like to sell",
            "all of the Equipment of this grade,",
            "please use the Sell [Bulk] button below.",
        ),
    ) == ("Laoku's Fatal Armor", EquipmentBulkGroup.EQUIPMENT_GRADE, None)


def test_confirmation_parser_rejects_missing_bulk_language_and_unknown_type():
    assert parse_confirmation("Selling [Gloves].", ("Sell now",)) is None
    assert parse_confirmation(
        "Selling [Thing].", ("Sell Bulk all of the [Boofs] of this grade",)
    ) is None


# Pure authorization matrix.


@pytest.mark.parametrize("equipment_type", sorted(CONFIGURABLE_EQUIPMENT_TYPES, key=lambda v: v.value))
@pytest.mark.parametrize("grade", sorted(DISPOSABLE_GRADES, key=lambda v: v.value))
@pytest.mark.parametrize("enhance", [False, True])
def test_policy_allows_only_positive_complete_allowlist_matches(equipment_type, grade, enhance):
    authorization = EquipmentSellAuthorization(
        frozenset({equipment_type}),
        frozenset({grade}),
        frozenset({enhance}),
        frozenset({EquipmentBulkGroup.EQUIPMENT_GRADE}),
        label="matrix",
    )
    assert authorization.allows(
        _item(
            name=f"{equipment_type.value} item" + (" (Enhance)" if enhance else ""),
            grade=grade,
            equipment_type=equipment_type,
            enhance=enhance,
        )
    )
    assert not authorization.allows(_item(grade=grade, equipment_type=equipment_type, enhance=not enhance))


@pytest.mark.parametrize("grade", [EquipmentGrade.ETHEREAL_PLUS, EquipmentGrade.UNKNOWN])
def test_ethereal_plus_and_unknown_grades_are_protected(grade):
    assert not _authorization().allows(_item(grade=grade))


def test_ethereal_non_accessory_can_be_explicitly_authorized():
    authorization = _authorization(
        allowed_grades=frozenset({EquipmentGrade.ETHEREAL}),
        allowed_enhance_states=frozenset({False}),
        allowed_bulk_groups=frozenset({EquipmentBulkGroup.TYPE_GRADE}),
    )
    assert authorization.allows(
        _item(grade=EquipmentGrade.ETHEREAL, enhance=False)
    )


@pytest.mark.parametrize("equipment_type", list(PROTECTED_ACCESSORY_TYPES) + [EquipmentType.UNKNOWN])
def test_accessories_and_unknown_type_are_protected(equipment_type):
    assert not _authorization().allows(_item(equipment_type=equipment_type))


def test_contradictory_or_unconfirmed_item_is_denied():
    assert not _authorization().allows(_item(contradictory=True))
    assert not _authorization().allows(_item(confirmed=False))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_types": frozenset({EquipmentType.RING})},
        {"allowed_types": frozenset({EquipmentType.UNKNOWN})},
        {"allowed_grades": frozenset({EquipmentGrade.ETHEREAL_PLUS})},
        {"allowed_grades": frozenset({EquipmentGrade.UNKNOWN})},
        {"allowed_bulk_groups": frozenset()},
        {"allowed_bulk_groups": frozenset({"equipment_grade"})},
    ],
)
def test_authorization_rejects_unsupported_or_protected_configuration(kwargs):
    with pytest.raises(ValueError):
        _authorization(**kwargs)


def test_consensus_requires_two_strictly_new_agreeing_samples():
    assert consensus_facts([_inventory(sequence=1, confirmed=False)]) is None
    result = consensus_facts(
        [_inventory(sequence=1, confirmed=False), _inventory(sequence=2, confirmed=False)]
    )
    assert result is not None and result.confirmed and result.sample_sequences == (1, 2)
    assert consensus_facts(
        [_inventory(count=120, sequence=1, confirmed=False), _inventory(count=119, sequence=2, confirmed=False)]
    ) is None


# Verified one-shot operation.


def test_item_count_decrease_is_success_with_one_confirm():
    script = _Script()
    result = _execute(script)
    assert result.outcome is EquipmentSellOutcome.SUCCESS
    assert result.before.item_count == 120 and result.after.item_count == 119
    assert result.confirm_count == 1
    assert [name for name, _ in script.inputs].count("confirm_bulk") == 1


@pytest.mark.parametrize("after_count", [120, 121])
def test_unchanged_or_increased_item_count_fails_closed(after_count):
    script = _Script(inventories=[_inventory(count=after_count, sequence=10)])
    result = _execute(script)
    assert result.outcome is EquipmentSellOutcome.FAILED
    assert result.reason == "post_item_count_did_not_decrease"
    assert result.confirm_count == 1


@pytest.mark.parametrize("after", [None, _inventory(count=119, sequence=8), _inventory(count=119, sequence=10, confirmed=False)])
def test_unreadable_stale_or_unconfirmed_post_count_is_not_success(after):
    script = _Script(inventories=[after])
    result = _execute(script)
    assert result.outcome is EquipmentSellOutcome.FAILED
    assert result.reason == "post_item_count_unreadable_or_stale"
    assert result.confirm_count == 1


def test_candidate_detail_mismatch_aborts_before_popup_and_destructive_input():
    script = _Script(
        details=[_item(sequence=4), _item(name="Other Gloves (Enhance)", sequence=6)]
    )
    result = _execute(script)
    assert result.outcome is EquipmentSellOutcome.DENIED
    assert result.reason == "candidate_detail_mismatch"
    assert [name for name, _ in script.inputs] == ["select"]
    assert result.confirm_count == 0


def test_confirmation_item_mismatch_cancels_without_confirm():
    script = _Script(confirmations=[_confirmation(name="Other Gloves", sequence=8)])
    result = _execute(script)
    assert result.reason == "confirmation_item_mismatch"
    assert [name for name, _ in script.inputs][-1] == "cancel"
    assert result.confirm_count == 0


def test_low_grade_enhance_requires_separate_enhance_group():
    request = _request(
        authorization=_authorization(
            allowed_bulk_groups=frozenset({EquipmentBulkGroup.ENHANCE_GRADE})
        ),
    )
    script = _Script(
        confirmations=[
            _confirmation(group=EquipmentBulkGroup.EQUIPMENT_GRADE, group_type=None)
        ]
    )
    result = _execute(script, request=request)
    assert result.outcome is EquipmentSellOutcome.DENIED
    assert result.reason == "bulk_group_mismatch"
    assert [name for name, _ in script.inputs][-1] == "cancel"
    assert result.confirm_count == 0


def test_low_grade_non_enhance_accepts_only_equipment_grade_group():
    authorization = _authorization(
        allowed_types=frozenset({EquipmentType.CHEST}),
        allowed_enhance_states=frozenset({False}),
        allowed_bulk_groups=frozenset({EquipmentBulkGroup.EQUIPMENT_GRADE}),
    )
    item = _item(name="Laoku's Fatal Armor", equipment_type=EquipmentType.CHEST, enhance=False)
    matching = _confirmation(
        name="Laoku's Fatal Armor",
        group=EquipmentBulkGroup.EQUIPMENT_GRADE,
        group_type=None,
    )
    wrong = _confirmation(
        name="Laoku's Fatal Armor",
        group=EquipmentBulkGroup.ENHANCE_GRADE,
        group_type=None,
    )
    assert authorization.allows_bulk(item, matching)
    assert not authorization.allows_bulk(item, wrong)


def test_ethereal_bulk_requires_exact_non_accessory_group_type():
    authorization = _authorization(
        allowed_grades=frozenset({EquipmentGrade.ETHEREAL}),
        allowed_enhance_states=frozenset({False}),
        allowed_bulk_groups=frozenset({EquipmentBulkGroup.TYPE_GRADE}),
    )
    item = _item(grade=EquipmentGrade.ETHEREAL, enhance=False)
    matching = _confirmation(
        group=EquipmentBulkGroup.TYPE_GRADE,
        group_type=EquipmentType.GLOVES,
    )
    mismatch = _confirmation(
        group=EquipmentBulkGroup.TYPE_GRADE,
        group_type=EquipmentType.BOOTS,
    )
    assert authorization.allows_bulk(item, matching)
    assert not authorization.allows_bulk(item, mismatch)


def test_ethereal_enhance_or_grade_wide_group_is_denied():
    authorization = _authorization(
        allowed_grades=frozenset({EquipmentGrade.ETHEREAL}),
        allowed_bulk_groups=frozenset(
            {EquipmentBulkGroup.TYPE_GRADE, EquipmentBulkGroup.ENHANCE_GRADE}
        ),
    )
    assert not authorization.allows_bulk(
        _item(grade=EquipmentGrade.ETHEREAL),
        _confirmation(group=EquipmentBulkGroup.ENHANCE_GRADE, group_type=None),
    )


def test_cancel_after_popup_propagates_and_never_confirms():
    calls = iter([False, False, True])
    script = _Script()
    result = _execute(script, cancel=lambda: next(calls))
    assert result.outcome is EquipmentSellOutcome.CANCELLED
    assert [name for name, _ in script.inputs][-1] == "cancel"
    assert result.confirm_count == 0


def test_stale_or_contradictory_initial_facts_produce_zero_input():
    for before in (
        _inventory(confirmed=False),
        EquipmentInventoryFact(120, 112, 7, 22, 2, 2.0, (1, 2), (), True),
    ):
        script = _Script()
        result = _execute(script, before=before)
        assert result.outcome is EquipmentSellOutcome.DENIED
        assert script.inputs == []


def test_candidate_outside_capacity_blocks_karat_page_with_zero_input():
    script = _Script()
    result = _execute(
        script,
        request=_request(candidate=EquipmentSellCandidate(8, 0)),
    )
    assert result.reason == "candidate_outside_acquired_capacity"
    assert script.inputs == []


def test_wrong_current_page_produces_zero_input():
    script = _Script()
    result = _execute(script, request=_request(candidate=EquipmentSellCandidate(6, 0)))
    assert result.reason == "candidate_page_not_current"
    assert script.inputs == []


def test_no_neighbor_system_or_composer_imports_and_no_scan_loop():
    root = Path(__file__).resolve().parents[1]
    source = (root / "bot" / "equipment_sell_operation.py").read_text(encoding="utf-8").lower()
    for forbidden in (
        "import bot.craft", "import bot.monster_wave", "import bot.keys_promotion",
        "import bot.trading", "import bot.treasure", "import bot.equipment_combine",
        "karat", "open_capacity", "while ",
    ):
        assert forbidden not in source


def test_equipment_sell_vocabulary_is_bulk_only():
    import bot.semantic_actions as actions

    exported = set(actions.__all__)
    assert "ConfirmEquipmentBulkSale" in exported
    assert "ConfirmEquipmentSingleSale" not in exported
    assert "EquipmentSellMode" not in (
        Path(__file__).resolve().parents[1] / "bot" / "equipment_sell_operation.py"
    ).read_text(encoding="utf-8")
