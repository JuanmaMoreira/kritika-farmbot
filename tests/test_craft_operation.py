from dataclasses import replace

import pytest

from bot.craft_operation import CraftOutcome, execute_craft
from bot.craft_policy import CraftQuantityMode, CraftRequest
from bot.craft_semantics import (
    CraftContextFact,
    CraftCurrency,
    CraftFamily,
    CraftItemType,
    CraftRecipeFact,
    CraftResultFact,
    CraftTier,
)


NOW = 100.0


def context(*, sequence=2, weapon=325, armor=734, accessory=645, observed_at=NOW, contradictory=False):
    return CraftContextFact(
        title="Craft",
        rate_label="Rate",
        expert_label="Expert Craft",
        weapon_material=weapon,
        armor_material=armor,
        accessory_material=accessory,
        weapon_capacity=999,
        armor_capacity=999,
        accessory_capacity=999,
        weapon_hero_cost=49,
        armor_hero_cost=49,
        accessory_hero_cost=49,
        sequence=sequence,
        observed_at=observed_at,
        sample_sequences=(sequence - 1, sequence),
        contradictory=contradictory,
    )


def recipe(
    *, sequence=4, family=CraftFamily.WEAPON, tier=CraftTier.HERO,
    currency=CraftCurrency.MATERIAL, quantity=1, contradictory=False,
):
    item = {
        CraftFamily.WEAPON: CraftItemType.WEAPON,
        CraftFamily.ARMOR: CraftItemType.HELMET,
        CraftFamily.ACCESSORY: CraftItemType.EARRINGS,
    }[family]
    return CraftRecipeFact(
        family=family,
        tier=tier,
        item_type=item,
        currency=currency,
        unit_cost=49,
        quantity=quantity,
        quantity_cap=10,
        sequence=sequence,
        observed_at=NOW,
        sample_sequences=(sequence - 1, sequence),
        contradictory=contradictory,
    )


def result_fact(sequence=6):
    return CraftResultFact(
        marker="Craft Result",
        sequence=sequence,
        observed_at=NOW,
        sample_sequences=(sequence - 1, sequence),
    )


def run_operation(
    *, request=None, before=None, recipes=None, result=None, after=None,
    cancelled=lambda: False,
):
    inputs = []
    recipes = list(recipes if recipes is not None else [recipe()])
    value = execute_craft(
        request=request or CraftRequest(CraftFamily.WEAPON),
        before=before or context(),
        open_recipe=lambda: inputs.append("open"),
        read_recipe=lambda: recipes.pop(0) if recipes else None,
        select_max=lambda: inputs.append("max"),
        cancel_recipe=lambda: inputs.append("cancel"),
        confirm_material=lambda: inputs.append("confirm"),
        read_result=lambda: result if result is not None else result_fact(),
        dismiss_result=lambda: inputs.append("dismiss"),
        read_context=lambda: after if after is not None else context(sequence=8, weapon=276),
        read_currency_boundary=lambda: None,
        reject_karats=lambda: inputs.append("reject_karats"),
        cancel_requested=cancelled,
        clock=lambda: NOW,
    )
    return value, inputs


def test_valid_non_premium_request_executes_one_bounded_action_and_verifies_material():
    outcome, physical = run_operation()

    assert outcome.outcome is CraftOutcome.SUCCESS
    assert outcome.inputs == ("open_recipe", "confirm_material", "dismiss_result")
    assert physical == ["open", "confirm", "dismiss"]
    assert outcome.after_fact.weapon_material == 276


def test_max_quantity_uses_one_verified_double_arrow_and_no_repeat():
    selected = recipe(sequence=6, quantity=6)
    after = context(sequence=10, weapon=31)

    outcome, physical = run_operation(
        request=CraftRequest(CraftFamily.WEAPON, quantity_mode=CraftQuantityMode.MAX_AVAILABLE),
        recipes=[recipe(sequence=4), selected],
        result=result_fact(sequence=8),
        after=after,
    )

    assert outcome.outcome is CraftOutcome.SUCCESS
    assert physical == ["open", "max", "confirm", "dismiss"]
    assert physical.count("max") == 1
    assert physical.count("confirm") == 1


def test_karat_recipe_boundary_cancels_before_confirm():
    outcome, physical = run_operation(
        recipes=[recipe(currency=CraftCurrency.KARATS)],
    )

    assert outcome.outcome is CraftOutcome.PREMIUM_BLOCKED
    assert physical == ["open", "cancel"]
    assert "confirm" not in physical


@pytest.mark.parametrize(
    "bad_before",
    (
        context(observed_at=NOW - 10),
        context(contradictory=True),
        replace(context(), sample_sequences=(2,)),
    ),
)
def test_stale_contradictory_or_unconfirmed_context_authorizes_zero_input(bad_before):
    outcome, physical = run_operation(before=bad_before)

    assert outcome.outcome is CraftOutcome.FAILED
    assert physical == []


def test_contradictory_recipe_fails_closed_before_confirm():
    outcome, physical = run_operation(recipes=[recipe(contradictory=True)])

    assert outcome.outcome is CraftOutcome.FAILED
    assert physical == ["open", "cancel"]


def test_unsupported_tier_authorizes_zero_input():
    outcome, physical = run_operation(
        request=CraftRequest(CraftFamily.WEAPON, tier=CraftTier.ARTISAN)
    )

    assert outcome.outcome is CraftOutcome.UNSUPPORTED
    assert physical == []


def test_unchanged_material_is_not_success_and_does_not_retry():
    outcome, physical = run_operation(after=context(sequence=8, weapon=325))

    assert outcome.outcome is CraftOutcome.NO_EFFECT
    assert physical == ["open", "confirm", "dismiss"]
    assert physical.count("confirm") == 1


def test_stale_result_never_authorizes_dismiss_or_retry():
    outcome, physical = run_operation(result=result_fact(sequence=4))

    assert outcome.outcome is CraftOutcome.FAILED
    assert physical == ["open", "confirm"]


def test_cancellation_propagates_with_zero_input_before_operation():
    outcome, physical = run_operation(cancelled=lambda: True)

    assert outcome.outcome is CraftOutcome.CANCELLED
    assert physical == []


def test_cancellation_after_selector_cancels_once_and_never_confirms():
    calls = iter((False, True))

    outcome, physical = run_operation(cancelled=lambda: next(calls, True))

    assert outcome.outcome is CraftOutcome.CANCELLED
    assert physical == ["open", "cancel"]
    assert "confirm" not in physical


def test_operation_vocabulary_has_no_scroll_or_relief_action():
    import bot.craft_operation as operation
    import bot.semantic_actions as actions

    source = open(operation.__file__, encoding="utf-8").read()
    exported = set(actions.__all__)

    assert "Swipe" not in source
    assert "EquipmentReliefComposer" not in source
    assert not any(name in exported for name in ("SpendCraftKarats", "ConfirmCraftKarats"))
