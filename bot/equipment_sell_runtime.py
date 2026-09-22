"""Equipment-specific live adapter for one verified sale.

The caller owns navigation and capture lifecycle.  This adapter only samples
the current Equipment Inventory surface, delegates policy/order to the pure
operation, and translates its four physical intents through ActionExecutor.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.equipment_sell_operation import (
    EquipmentSellOutcome,
    EquipmentSellRequest,
    EquipmentSellResult,
    execute_equipment_sell,
)
from bot.equipment_sell_semantics import consensus_facts
from bot.semantic_actions import (
    CancelEquipmentSale,
    ConfirmEquipmentBulkSale,
    OpenEquipmentSell,
    SelectEquipmentInventorySlot,
)


class EquipmentSellRuntime:
    """Run one sale from an already-open Equipment Inventory page."""

    def __init__(
        self,
        source,
        reader,
        actions: ActionExecutor,
        *,
        sample_timeout: float = 4.0,
        sample_interval: float = 0.05,
        cancel_requested: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(getattr(source, "get_frame", None)):
            raise ValueError("source must provide get_frame()")
        for method in ("inventory_sample", "detail_sample", "confirmation_sample"):
            if not callable(getattr(reader, method, None)):
                raise ValueError(f"reader must provide {method}()")
        if not isinstance(actions, ActionExecutor):
            raise ValueError("actions must be an ActionExecutor")
        if sample_timeout <= 0 or sample_interval < 0:
            raise ValueError("sampling durations must be positive/non-negative")
        if not all(callable(value) for value in (cancel_requested, clock, sleeper)):
            raise ValueError("runtime callbacks must be callable")
        self.source = source
        self.reader = reader
        self.actions = actions
        self.sample_timeout = float(sample_timeout)
        self.sample_interval = float(sample_interval)
        self.cancel_requested = cancel_requested
        self.clock = clock
        self.sleeper = sleeper
        self._latest = None
        self._after_sequence = 0

    def execute(self, request: EquipmentSellRequest) -> EquipmentSellResult:
        """Execute at most one confirm; never navigate, scan or retry input."""

        if not isinstance(request, EquipmentSellRequest):
            raise ValueError("request must be EquipmentSellRequest")
        before = self._read_consensus("inventory_sample", after_sequence=0)
        if before is None:
            return EquipmentSellResult(
                outcome=(
                    EquipmentSellOutcome.CANCELLED
                    if self.cancel_requested()
                    else EquipmentSellOutcome.FAILED
                ),
                reason=(
                    "cancelled"
                    if self.cancel_requested()
                    else "initial_inventory_unreadable"
                ),
            )
        self._after_sequence = before.sequence

        return execute_equipment_sell(
            request=request,
            before=before,
            select_candidate=lambda candidate: self._tap(
                SelectEquipmentInventorySlot(candidate.slot)
            ),
            read_detail=lambda: self._read_next("detail_sample"),
            open_confirmation=lambda: self._tap(OpenEquipmentSell()),
            read_confirmation=lambda: self._read_next("confirmation_sample"),
            confirm_bulk=lambda: self._tap(ConfirmEquipmentBulkSale()),
            cancel_confirmation=lambda: self._tap(CancelEquipmentSale()),
            read_inventory=lambda: self._read_next("inventory_sample"),
            cancel_requested=self.cancel_requested,
        )

    def _read_next(self, method_name: str):
        fact = self._read_consensus(
            method_name,
            after_sequence=self._after_sequence,
        )
        if fact is not None:
            self._after_sequence = fact.sequence
        return fact

    def _read_consensus(self, method_name: str, *, after_sequence: int):
        deadline = self.clock() + self.sample_timeout
        samples = []
        examined_sequences: set[int] = set()
        # OCR consensus still uses at most four recent positive samples.  The
        # physical Sell transition may expose many fresh animation frames
        # before Item Count becomes readable, so bound observation separately
        # instead of exhausting the read on the first four frames.
        while len(examined_sequences) < 48 and self.clock() < deadline:
            if self.cancel_requested():
                return None
            snapshot = self.source.get_frame()
            if (
                snapshot.sequence <= after_sequence
                or snapshot.sequence in examined_sequences
            ):
                self.sleeper(self.sample_interval)
                continue
            examined_sequences.add(snapshot.sequence)
            self._latest = snapshot
            sample = getattr(self.reader, method_name)(
                snapshot.image,
                sequence=snapshot.sequence,
                observed_at=snapshot.timestamp,
            )
            if sample is not None:
                samples.append(sample)
                samples = samples[-4:]
                consensus = consensus_facts(samples, required=2, max_samples=4)
                if consensus is not None:
                    return consensus
            self.sleeper(self.sample_interval)
        return None

    def _tap(self, action) -> None:
        if self._latest is None:
            raise RuntimeError("no fresh frame available for action geometry")
        self.actions.execute(
            action,
            FrameGeometry.from_frame(self._latest.image),
        )


__all__ = ("EquipmentSellRuntime",)
