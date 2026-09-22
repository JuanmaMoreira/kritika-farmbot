"""One bounded, verified Equipment sale against an explicit candidate.

The operation owns ordering and verification only.  Perception is injected as
fresh semantic reads and physical input is injected as small callbacks.  It
does not navigate into Inventory, scan multiple candidates, compose relief,
buy capacity or repeat a sale.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from numbers import Integral

from bot.equipment_sell_policy import (
    EquipmentSellAuthorization,
    confirmation_matches_item,
)
from bot.equipment_sell_semantics import (
    EquipmentInventoryFact,
    EquipmentItemFact,
    EquipmentSellConfirmationFact,
)


class EquipmentSellOutcome(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EquipmentSellCandidate:
    page: int
    slot: int

    def __post_init__(self) -> None:
        for name in ("page", "slot"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
        if self.page <= 0 or not 0 <= self.slot < 16:
            raise ValueError("candidate must name a positive page and 4x4 slot")


@dataclass(frozen=True)
class EquipmentSellRequest:
    authorization: EquipmentSellAuthorization
    candidate: EquipmentSellCandidate

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, EquipmentSellAuthorization):
            raise ValueError("authorization must be EquipmentSellAuthorization")
        if not isinstance(self.candidate, EquipmentSellCandidate):
            raise ValueError("candidate must be EquipmentSellCandidate")


@dataclass(frozen=True)
class EquipmentSellResult:
    outcome: EquipmentSellOutcome
    reason: str
    before: EquipmentInventoryFact | None = None
    item: EquipmentItemFact | None = None
    confirmation: EquipmentSellConfirmationFact | None = None
    after: EquipmentInventoryFact | None = None
    inputs: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.outcome is EquipmentSellOutcome.SUCCESS

    @property
    def confirm_count(self) -> int:
        return self.inputs.count("confirm_bulk")


def execute_equipment_sell(
    *,
    request: EquipmentSellRequest,
    before: EquipmentInventoryFact,
    select_candidate: Callable[[EquipmentSellCandidate], None],
    read_detail: Callable[[], EquipmentItemFact | None],
    open_confirmation: Callable[[], None],
    read_confirmation: Callable[[], EquipmentSellConfirmationFact | None],
    confirm_bulk: Callable[[], None],
    cancel_confirmation: Callable[[], None],
    read_inventory: Callable[[], EquipmentInventoryFact | None],
    cancel_requested: Callable[[], bool] = lambda: False,
) -> EquipmentSellResult:
    """Execute at most one irreversible confirmation and verify Item Count.

    ``before`` and every reader result must already be a consensus fact.  The
    operation additionally enforces strict sequence progress at every boundary.
    No callback is retried.
    """

    _validate_io(
        request,
        before,
        select_candidate,
        read_detail,
        open_confirmation,
        read_confirmation,
        confirm_bulk,
        cancel_confirmation,
        read_inventory,
        cancel_requested,
    )
    inputs: list[str] = []
    if cancel_requested():
        return _result(EquipmentSellOutcome.CANCELLED, "cancelled", before, inputs)
    precondition = _precondition_error(request, before)
    if precondition is not None:
        return _result(EquipmentSellOutcome.DENIED, precondition, before, inputs)

    try:
        select_candidate(request.candidate)
        inputs.append("select_candidate")
        first = read_detail()
        if not _fresh_confirmed(first, after_sequence=before.sequence):
            return _result(
                EquipmentSellOutcome.FAILED,
                "detail_unreadable_or_stale",
                before,
                inputs,
            )
        assert isinstance(first, EquipmentItemFact)
        if not request.authorization.allows(first):
            return _result(
                EquipmentSellOutcome.DENIED,
                "item_not_authorized",
                before,
                inputs,
                item=first,
            )

        # A second complete consensus immediately before opening Sell prevents
        # a stale selected item or detail transition from authorizing the popup.
        second = read_detail()
        if not _fresh_confirmed(second, after_sequence=first.sequence):
            return _result(
                EquipmentSellOutcome.FAILED,
                "detail_reverification_failed",
                before,
                inputs,
                item=first,
            )
        assert isinstance(second, EquipmentItemFact)
        if _item_key(second) != _item_key(first) or not request.authorization.allows(second):
            return _result(
                EquipmentSellOutcome.DENIED,
                "candidate_detail_mismatch",
                before,
                inputs,
                item=second,
            )
        if cancel_requested():
            return _result(
                EquipmentSellOutcome.CANCELLED,
                "cancelled",
                before,
                inputs,
                item=second,
            )

        open_confirmation()
        inputs.append("open_confirmation")
        confirmation = read_confirmation()
        if not _fresh_confirmed(confirmation, after_sequence=second.sequence):
            return _cancel_result(
                EquipmentSellOutcome.FAILED,
                "confirmation_unreadable_or_stale",
                before,
                second,
                confirmation,
                inputs,
                cancel_confirmation,
            )
        assert isinstance(confirmation, EquipmentSellConfirmationFact)
        if not confirmation_matches_item(confirmation, second):
            return _cancel_result(
                EquipmentSellOutcome.FAILED,
                "confirmation_item_mismatch",
                before,
                second,
                confirmation,
                inputs,
                cancel_confirmation,
            )
        if not request.authorization.allows_bulk(second, confirmation):
            return _cancel_result(
                EquipmentSellOutcome.DENIED,
                "bulk_group_mismatch",
                before,
                second,
                confirmation,
                inputs,
                cancel_confirmation,
            )
        if cancel_requested():
            return _cancel_result(
                EquipmentSellOutcome.CANCELLED,
                "cancelled",
                before,
                second,
                confirmation,
                inputs,
                cancel_confirmation,
            )

        confirm_bulk()
        inputs.append("confirm_bulk")

        after = read_inventory()
        if not _fresh_confirmed(after, after_sequence=confirmation.sequence):
            return _result(
                EquipmentSellOutcome.FAILED,
                "post_item_count_unreadable_or_stale",
                before,
                inputs,
                item=second,
                confirmation=confirmation,
                after=after,
            )
        assert isinstance(after, EquipmentInventoryFact)
        if after.capacity != before.capacity:
            reason = "post_capacity_changed"
        elif after.item_count >= before.item_count:
            reason = "post_item_count_did_not_decrease"
        else:
            return _result(
                EquipmentSellOutcome.SUCCESS,
                "item_count_decreased",
                before,
                inputs,
                item=second,
                confirmation=confirmation,
                after=after,
            )
        return _result(
            EquipmentSellOutcome.FAILED,
            reason,
            before,
            inputs,
            item=second,
            confirmation=confirmation,
            after=after,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        return _result(
            EquipmentSellOutcome.FAILED,
            f"{type(error).__name__}: {error}",
            before,
            inputs,
        )


def _precondition_error(
    request: EquipmentSellRequest, before: EquipmentInventoryFact
) -> str | None:
    if not before.confirmed:
        return "inventory_unconfirmed"
    candidate = request.candidate
    tail_page, tail_slot = divmod(before.capacity - 1, 16)
    tail_page += 1
    if candidate.page > tail_page or (
        candidate.page == tail_page and candidate.slot > tail_slot
    ):
        return "candidate_outside_acquired_capacity"
    if candidate.page != before.page:
        return "candidate_page_not_current"
    return None


def _fresh_confirmed(fact, *, after_sequence: int) -> bool:
    return fact is not None and fact.confirmed and fact.sequence > after_sequence


def _item_key(item: EquipmentItemFact) -> tuple[object, ...]:
    return (
        " ".join(item.name.casefold().split()),
        item.grade,
        item.equipment_type,
        item.enhance,
    )


def _cancel_result(
    outcome,
    reason,
    before,
    item,
    confirmation,
    inputs,
    cancel_confirmation,
) -> EquipmentSellResult:
    try:
        cancel_confirmation()
        inputs.append("cancel_confirmation")
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        return _result(
            EquipmentSellOutcome.FAILED,
            f"cancel_failed:{type(error).__name__}",
            before,
            inputs,
            item=item,
            confirmation=confirmation,
        )
    return _result(
        outcome,
        reason,
        before,
        inputs,
        item=item,
        confirmation=confirmation,
    )


def _result(outcome, reason, before, inputs, *, item=None, confirmation=None, after=None):
    return EquipmentSellResult(
        outcome=outcome,
        reason=reason,
        before=before,
        item=item,
        confirmation=confirmation,
        after=after,
        inputs=tuple(inputs),
    )


def _validate_io(request, before, *callbacks) -> None:
    if not isinstance(request, EquipmentSellRequest):
        raise ValueError("request must be EquipmentSellRequest")
    if not isinstance(before, EquipmentInventoryFact):
        raise ValueError("before must be EquipmentInventoryFact")
    if any(not callable(callback) for callback in callbacks):
        raise ValueError("operation IO must be callable")


__all__ = (
    "EquipmentSellCandidate",
    "EquipmentSellOutcome",
    "EquipmentSellRequest",
    "EquipmentSellResult",
    "execute_equipment_sell",
)
