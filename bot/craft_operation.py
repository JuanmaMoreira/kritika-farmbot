"""Pure, bounded execution of one verified non-premium Craft action."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import time

from bot.craft_policy import CraftQuantityMode, CraftRequest, requested_quantity
from bot.craft_semantics import (
    CraftContextFact,
    CraftCurrency,
    CraftCurrencyBoundaryFact,
    CraftRecipeFact,
    CraftResultFact,
)


class CraftOutcome(str, Enum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_MATERIAL = "insufficient_material"
    PREMIUM_BLOCKED = "premium_blocked"
    NO_EFFECT = "no_effect"
    FAILED = "failed"


@dataclass(frozen=True)
class CraftOperationResult:
    outcome: CraftOutcome
    before_fact: CraftContextFact | None = None
    recipe_fact: CraftRecipeFact | None = None
    after_fact: CraftContextFact | None = None
    reason: str | None = None
    inputs: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


def execute_craft(
    *,
    request: CraftRequest,
    before: CraftContextFact,
    open_recipe: Callable[[], None],
    read_recipe: Callable[[], CraftRecipeFact | None],
    select_max: Callable[[], None],
    cancel_recipe: Callable[[], None],
    confirm_material: Callable[[], None],
    read_result: Callable[[], CraftResultFact | None],
    dismiss_result: Callable[[], None],
    read_context: Callable[[], CraftContextFact | None],
    read_currency_boundary: Callable[[], CraftCurrencyBoundaryFact | None],
    reject_karats: Callable[[], None],
    cancel_requested: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    max_fact_age: float = 5.0,
) -> CraftOperationResult:
    """Authorize one confirm at most; no retry, scroll, or relief ownership."""

    callbacks = (
        open_recipe, read_recipe, select_max, cancel_recipe, confirm_material,
        read_result, dismiss_result, read_context, read_currency_boundary,
        reject_karats, cancel_requested, clock,
    )
    if not isinstance(request, CraftRequest):
        raise ValueError("request must be CraftRequest")
    if not isinstance(before, CraftContextFact):
        raise ValueError("before must be CraftContextFact")
    if not all(callable(value) for value in callbacks):
        raise ValueError("operation callbacks must be callable")
    if max_fact_age <= 0:
        raise ValueError("max_fact_age must be positive")

    inputs: list[str] = []
    evidence: list[str] = []
    if cancel_requested():
        return _finish(CraftOutcome.CANCELLED, before, inputs, evidence, "cancelled")
    if not request.supported:
        return _finish(CraftOutcome.UNSUPPORTED, before, inputs, evidence, "unsupported_recipe")
    if not _fresh_confirmed(before, clock(), max_fact_age):
        return _finish(CraftOutcome.FAILED, before, inputs, evidence, "stale_or_unconfirmed_context")

    screen_cost = before.hero_cost_for(request.family)
    screen_material = before.material_for(request.family)
    initial_target = requested_quantity(
        request,
        material=screen_material,
        unit_cost=screen_cost,
        ui_cap=10,
    )
    if initial_target is None:
        return _finish(
            CraftOutcome.INSUFFICIENT_MATERIAL,
            before,
            inputs,
            evidence,
            "insufficient_material_before_selector",
        )

    try:
        open_recipe()
    except Exception as error:
        return _finish(CraftOutcome.FAILED, before, inputs, evidence, f"open_recipe_failed:{type(error).__name__}")
    inputs.append("open_recipe")
    recipe = read_recipe()
    if (
        recipe is None
        or not _fresh_confirmed(recipe, clock(), max_fact_age)
        or recipe.sequence <= before.sequence
        or recipe.family is not request.family
        or recipe.tier is not request.tier
        or recipe.unit_cost != screen_cost
        or recipe.quantity != 1
        or recipe.quantity_cap != 10
    ):
        _cancel_once(cancel_recipe, inputs)
        return CraftOperationResult(
            CraftOutcome.FAILED,
            before_fact=before,
            recipe_fact=recipe,
            reason="recipe_verification_failed",
            inputs=tuple(inputs),
            evidence=tuple(evidence),
        )
    if recipe.currency is not CraftCurrency.MATERIAL:
        _cancel_once(cancel_recipe, inputs)
        return CraftOperationResult(
            CraftOutcome.PREMIUM_BLOCKED,
            before_fact=before,
            recipe_fact=recipe,
            reason="non_material_currency",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, f"currency:{recipe.currency.value}"]),
        )
    evidence.append(
        f"recipe:{recipe.family.value}:{recipe.tier.value}:"
        f"{recipe.unit_cost}:{recipe.quantity}/{recipe.quantity_cap}"
    )

    target = requested_quantity(
        request,
        material=screen_material,
        unit_cost=recipe.unit_cost,
        ui_cap=recipe.quantity_cap,
    )
    if target is None:
        _cancel_once(cancel_recipe, inputs)
        return CraftOperationResult(
            CraftOutcome.INSUFFICIENT_MATERIAL,
            before_fact=before,
            recipe_fact=recipe,
            reason="insufficient_material",
            inputs=tuple(inputs),
            evidence=tuple(evidence),
        )

    selected = recipe
    if request.quantity_mode is CraftQuantityMode.MAX_AVAILABLE and target > 1:
        if cancel_requested():
            _cancel_once(cancel_recipe, inputs)
            return CraftOperationResult(
                CraftOutcome.CANCELLED, before_fact=before, recipe_fact=recipe,
                reason="cancelled", inputs=tuple(inputs), evidence=tuple(evidence),
            )
        try:
            select_max()
        except Exception as error:
            _cancel_once(cancel_recipe, inputs)
            return CraftOperationResult(
                CraftOutcome.FAILED, before_fact=before, recipe_fact=recipe,
                reason=f"select_max_failed:{type(error).__name__}",
                inputs=tuple(inputs), evidence=tuple(evidence),
            )
        inputs.append("select_max")
        selected = read_recipe()
        if (
            selected is None
            or not _fresh_confirmed(selected, clock(), max_fact_age)
            or selected.sequence <= recipe.sequence
            or selected.family is not request.family
            or selected.tier is not request.tier
            or selected.currency is not CraftCurrency.MATERIAL
            or selected.unit_cost != recipe.unit_cost
            or selected.quantity_cap != recipe.quantity_cap
            or selected.quantity != target
        ):
            _cancel_once(cancel_recipe, inputs)
            return CraftOperationResult(
                CraftOutcome.FAILED, before_fact=before, recipe_fact=selected,
                reason="max_quantity_verification_failed",
                inputs=tuple(inputs), evidence=tuple(evidence),
            )
        evidence.append(f"quantity:{selected.quantity}/{selected.quantity_cap}")

    if screen_material < selected.unit_cost * selected.quantity:
        _cancel_once(cancel_recipe, inputs)
        return CraftOperationResult(
            CraftOutcome.PREMIUM_BLOCKED,
            before_fact=before,
            recipe_fact=selected,
            reason="karat_boundary_predicted",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "karat_guard:material_shortfall"]),
        )
    if cancel_requested():
        _cancel_once(cancel_recipe, inputs)
        return CraftOperationResult(
            CraftOutcome.CANCELLED, before_fact=before, recipe_fact=selected,
            reason="cancelled", inputs=tuple(inputs), evidence=tuple(evidence),
        )

    try:
        confirm_material()
    except Exception as error:
        return CraftOperationResult(
            CraftOutcome.FAILED, before_fact=before, recipe_fact=selected,
            reason=f"confirm_failed:{type(error).__name__}",
            inputs=tuple(inputs), evidence=tuple(evidence),
        )
    inputs.append("confirm_material")

    result = read_result()
    if result is None:
        if cancel_requested():
            return CraftOperationResult(
                CraftOutcome.CANCELLED, before_fact=before, recipe_fact=selected,
                reason="cancelled_after_confirm", inputs=tuple(inputs), evidence=tuple(evidence),
            )
        boundary = read_currency_boundary()
        if (
            boundary is not None
            and _fresh_confirmed(boundary, clock(), max_fact_age)
            and boundary.sequence > selected.sequence
        ):
            reject_karats()
            inputs.append("reject_karats")
            return CraftOperationResult(
                CraftOutcome.PREMIUM_BLOCKED,
                before_fact=before,
                recipe_fact=selected,
                reason="karat_boundary_observed",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, f"karats:{boundary.karat_cost}"]),
            )
        return CraftOperationResult(
            CraftOutcome.FAILED, before_fact=before, recipe_fact=selected,
            reason="result_unreadable", inputs=tuple(inputs), evidence=tuple(evidence),
        )
    if not _fresh_confirmed(result, clock(), max_fact_age) or result.sequence <= selected.sequence:
        return CraftOperationResult(
            CraftOutcome.FAILED, before_fact=before, recipe_fact=selected,
            reason="stale_or_unconfirmed_result", inputs=tuple(inputs), evidence=tuple(evidence),
        )
    if cancel_requested():
        return CraftOperationResult(
            CraftOutcome.CANCELLED, before_fact=before, recipe_fact=selected,
            reason="cancelled_after_confirm", inputs=tuple(inputs), evidence=tuple(evidence),
        )
    dismiss_result()
    inputs.append("dismiss_result")
    after = read_context()
    if (
        after is None
        or not _fresh_confirmed(after, clock(), max_fact_age)
        or after.sequence <= result.sequence
    ):
        return CraftOperationResult(
            CraftOutcome.FAILED, before_fact=before, recipe_fact=selected,
            after_fact=after, reason="stable_craft_not_restored",
            inputs=tuple(inputs), evidence=tuple(evidence),
        )
    expected_material = screen_material - selected.unit_cost * selected.quantity
    actual_material = after.material_for(request.family)
    outcome = CraftOutcome.SUCCESS if actual_material == expected_material else CraftOutcome.NO_EFFECT
    return CraftOperationResult(
        outcome,
        before_fact=before,
        recipe_fact=selected,
        after_fact=after,
        reason=None if outcome is CraftOutcome.SUCCESS else "material_change_not_verified",
        inputs=tuple(inputs),
        evidence=tuple([*evidence, f"material:{screen_material}->{actual_material}"]),
    )


def _fresh_confirmed(fact, now: float, max_age: float) -> bool:
    return bool(fact.confirmed and 0.0 <= now - fact.observed_at <= max_age)


def _cancel_once(cancel_recipe: Callable[[], None], inputs: list[str]) -> None:
    try:
        cancel_recipe()
    except Exception:
        return
    inputs.append("cancel_recipe")


def _finish(outcome, before, inputs, evidence, reason) -> CraftOperationResult:
    return CraftOperationResult(
        outcome, before_fact=before, reason=reason,
        inputs=tuple(inputs), evidence=tuple(evidence),
    )


__all__ = (
    "CraftOperationResult", "CraftOutcome", "execute_craft",
)
