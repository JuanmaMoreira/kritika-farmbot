from dataclasses import dataclass

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.black_market_flow import BlackMarketFlow
from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_INSUFFICIENT_GOLD,
    POPUP_INVENTORY_FULL,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
    SCREEN_LOBBY,
)
from bot.observations import ObservationBatch
from bot.flow_contracts import FlowEvent, FlowStatus
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    AcknowledgeInventoryFull,
    CloseBlackMarket,
    OpenBlackMarket,
    RejectInsufficientGold,
    SelectBlackMarketSlot,
)
from bot.state import ResolutionStatus, ResolvedState


class ScriptedObserver:
    def __init__(self, observes, waits):
        self.observes = list(observes)
        self.waits = list(waits)
        self.wait_calls = []

    def observe(self):
        return self.observes.pop(0)

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        self.wait_calls.append((after_sequence, stable_for))
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item


class Actions:
    def __init__(self):
        self.actions = []

    def execute(self, action, geometry):
        self.actions.append(action)


class Events:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)


def _snapshot(
    sequence,
    *,
    base=None,
    overlays=(),
    gold=(),
    purchased=(),
    status=None,
):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    batch = ObservationBatch(sequence=sequence, timestamp=float(sequence))
    state = ResolvedState(
        status=status,
        sequence=sequence,
        timestamp=float(sequence),
        base_context=base,
        overlays=tuple(overlays),
        base_candidates=(
            (SCREEN_LOBBY, SCREEN_BLACK_MARKET)
            if status is ResolutionStatus.AMBIGUOUS
            else ()
        ),
    )
    return RuntimeSnapshot(
        frame=FrameSnapshot(
            image=np.zeros((1224, 2712, 3), dtype=np.uint8),
            sequence=sequence,
            timestamp=float(sequence),
        ),
        observations=batch,
        state=state,
        facts=RuntimeFacts(
            gold_slots=frozenset(gold),
            purchased_slots=frozenset(purchased),
        ),
        geometry=FrameGeometry(width=2712, height=1224),
    )


def _run(observes, waits, *, max_slots=None):
    observer = ScriptedObserver(observes, waits)
    actions = Actions()
    events = Events()
    result = BlackMarketFlow(observer, actions, events).run(
        max_slot_attempts=max_slots
    )
    return result, actions.actions, events.events, observer


def test_flow_requires_clean_lobby_and_never_navigates_generically():
    result, actions, events, _ = _run(
        [_snapshot(1, base=SCREEN_BLACK_MARKET)], []
    )

    assert result.status is FlowStatus.FAILED
    assert result.error == "precondition_lobby_failed"
    assert actions == []
    assert events == ["black_market.unexpected_state"]


def test_transient_unknown_lobby_precondition_settles_without_input():
    result, actions, events, observer = _run(
        [_snapshot(1)],
        [
            _snapshot(2, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
        max_slots=0,
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == (4,)
    assert actions == [OpenBlackMarket(), CloseBlackMarket()]
    assert events == []
    assert observer.wait_calls == [(1, 0.25), (2, 0.75), (3, 0.0)]


def test_lobby_to_black_market_with_zero_gold_is_successful_noop():
    result, actions, events, observer = _run(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET),
            RuntimeWaitTimeout(
                after_sequence=2,
                timeout=2.0,
                last_snapshot=_snapshot(3, base=SCREEN_BLACK_MARKET),
            ),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.succeeded
    assert actions == [OpenBlackMarket(), CloseBlackMarket()]
    assert events == ["black_market.no_gold"]
    assert observer.wait_calls == [(1, 0.75), (2, 0.0), (3, 0.0)]


def test_transient_empty_gold_read_is_confirmed_before_noop_decision():
    result, actions, events, observer = _run(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET),
            _snapshot(3, base=SCREEN_BLACK_MARKET, gold={2, 3, 5, 8}),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
        max_slots=0,
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == (2, 3, 5, 8)
    assert result.attempted_slots == ()
    assert actions == [OpenBlackMarket(), CloseBlackMarket()]
    assert events == []
    assert observer.wait_calls == [(1, 0.75), (2, 0.0), (3, 0.0)]


def test_open_black_market_retries_only_from_fresh_clean_lobby():
    result, actions, events, observer = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
        [
            RuntimeWaitTimeout(
                after_sequence=1,
                timeout=5.0,
                last_snapshot=_snapshot(2, base=SCREEN_LOBBY),
            ),
            RuntimeWaitTimeout(
                after_sequence=2,
                timeout=2.0,
                last_snapshot=_snapshot(3, base=SCREEN_LOBBY),
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(6, base=SCREEN_BLACK_MARKET),
            ),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert actions == [OpenBlackMarket(), OpenBlackMarket(), CloseBlackMarket()]
    assert events == ["black_market.no_gold"]
    assert observer.wait_calls == [
        (1, 0.75),
        (2, 0.75),
        (4, 0.75),
        (5, 0.0),
        (6, 0.0),
    ]


def test_purchase_confirmation_yes_and_same_slot_purchased_are_verified():
    result, actions, events, observer = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET, gold={4}),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, purchased={4}),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == (4,)
    assert result.attempted_slots == (4,)
    assert result.verified_purchases == (4,)
    assert result.insufficient_gold_count == 0
    assert actions == [
        OpenBlackMarket(),
        SelectBlackMarketSlot(4),
        AcceptPurchaseConfirmation(),
        CloseBlackMarket(),
    ]
    assert events == []
    assert observer.wait_calls == [
        (1, 0.75),
        (3, 0.0),
        (4, 0.0),
        (5, 0.0),
    ]


def test_multiple_gold_slots_are_attempted_in_deterministic_order():
    result, actions, _, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_BLACK_MARKET, gold={9}),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={7, 2}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, purchased={2}),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET, purchased={2, 7}),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.initial_gold_slots == (2, 7)
    assert result.attempted_slots == (2, 7)
    assert result.verified_purchases == (2, 7)
    assert [
        action.slot_index
        for action in actions
        if isinstance(action, SelectBlackMarketSlot)
    ] == [2, 7]


def test_insufficient_gold_logs_no_slot_rejects_and_continues():
    result, actions, events, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_BLACK_MARKET),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1, 8}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INSUFFICIENT_GOLD},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET, purchased={8}),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.attempted_slots == (1, 8)
    assert result.verified_purchases == (8,)
    assert result.insufficient_gold_count == 1
    assert result.events == (FlowEvent("low_gold"),)
    assert events == []
    assert actions == [
        OpenBlackMarket(),
        SelectBlackMarketSlot(1),
        RejectInsufficientGold(),
        SelectBlackMarketSlot(8),
        AcceptPurchaseConfirmation(),
        CloseBlackMarket(),
    ]


def test_inventory_full_logs_ok_and_continues_without_retrying_same_slot():
    result, actions, events, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_BLACK_MARKET),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1, 8}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET, purchased={8}),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.attempted_slots == (1, 8)
    assert result.verified_purchases == (8,)
    assert result.inventory_full_count == 1
    assert result.events == (FlowEvent("inventory_full"),)
    assert events == []
    assert actions == [
        OpenBlackMarket(),
        SelectBlackMarketSlot(1),
        AcknowledgeInventoryFull(),
        SelectBlackMarketSlot(8),
        AcceptPurchaseConfirmation(),
        CloseBlackMarket(),
    ]


def test_multiple_inventory_full_results_are_nonfatal_business_events():
    result, actions, events, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_BLACK_MARKET),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={2, 5}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.attempted_slots == (2, 5)
    assert result.inventory_full_count == 2
    assert result.events == (
        FlowEvent("inventory_full"),
        FlowEvent("inventory_full"),
    )
    assert events == []
    assert actions.count(AcknowledgeInventoryFull()) == 2


def test_low_gold_and_inventory_full_can_both_happen_for_one_character():
    result, actions, events, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_BLACK_MARKET),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={0, 9}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INSUFFICIENT_GOLD},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.insufficient_gold_count == 1
    assert result.inventory_full_count == 1
    assert result.events == (FlowEvent("low_gold"), FlowEvent("inventory_full"))
    assert events == []
    assert RejectInsufficientGold() in actions
    assert AcknowledgeInventoryFull() in actions


def test_inventory_full_ack_technical_failure_aborts_before_next_slot():
    still_open = _snapshot(
        5,
        base=SCREEN_BLACK_MARKET,
        overlays={POPUP_INVENTORY_FULL},
    )
    unknown = _snapshot(7)
    result, actions, events, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET),
            unknown,
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1, 8}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=5.0,
                last_snapshot=still_open,
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(6),
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert result.error.startswith("inventory_full_ack_failed")
    assert result.inventory_full_count == 1
    assert SelectBlackMarketSlot(8) not in actions
    assert result.events == (FlowEvent("inventory_full"),)
    assert events == ["black_market.unexpected_state"]


def test_flow_uses_initial_gold_read_once_and_ignores_later_changes():
    result, actions, _, _ = _run(
        [
            _snapshot(1, base=SCREEN_LOBBY),
            _snapshot(3, base=SCREEN_BLACK_MARKET, gold={9}),
            _snapshot(6, base=SCREEN_BLACK_MARKET, gold={9}),
        ],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={2, 5}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, purchased={2}),
            _snapshot(
                7,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(8, base=SCREEN_BLACK_MARKET, purchased={2, 5}),
            _snapshot(9, base=SCREEN_LOBBY),
        ],
    )

    assert result.initial_gold_slots == (2, 5)
    assert [
        action.slot_index
        for action in actions
        if isinstance(action, SelectBlackMarketSlot)
    ] == [2, 5]


def test_one_slot_smoke_limit_does_not_change_normal_slot_policy():
    result, actions, _, _ = _run(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(3, base=SCREEN_BLACK_MARKET)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={6, 2}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, purchased={2}),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
        max_slots=1,
    )

    assert result.initial_gold_slots == (2, 6)
    assert result.attempted_slots == (2,)
    assert [
        action.slot_index
        for action in actions
        if isinstance(action, SelectBlackMarketSlot)
    ] == [2]


def test_zero_attempt_debug_limit_opens_market_and_reports_initial_gold_only():
    result, actions, _, _ = _run(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1, 6}),
            _snapshot(3, base=SCREEN_LOBBY),
        ],
        max_slots=0,
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == (1, 6)
    assert result.initial_purchased_slots == ()
    assert result.attempted_slots == ()
    assert actions == [OpenBlackMarket(), CloseBlackMarket()]


def test_return_to_lobby_is_a_required_fresh_postcondition():
    timeout = RuntimeWaitTimeout(
        after_sequence=3,
        timeout=5.0,
        last_snapshot=_snapshot(4, base=SCREEN_BLACK_MARKET),
    )
    result, actions, events, observer = _run(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET),
            RuntimeWaitTimeout(
                after_sequence=2,
                timeout=2.0,
                last_snapshot=_snapshot(3, base=SCREEN_BLACK_MARKET),
            ),
            timeout,
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert result.error.startswith("return_to_lobby_failed")
    assert actions == [OpenBlackMarket(), CloseBlackMarket()]
    assert events == ["black_market.no_gold", "black_market.unexpected_state"]
    assert observer.wait_calls == [(1, 0.75), (2, 0.0), (3, 0.0)]


def test_purchase_unverified_logs_and_aborts_entire_flow():
    clean_without_purchased = _snapshot(5, base=SCREEN_BLACK_MARKET)
    timeout = RuntimeWaitTimeout(
        after_sequence=4,
        timeout=5.0,
        last_snapshot=clean_without_purchased,
    )
    result, actions, events, _ = _run(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(3, base=SCREEN_BLACK_MARKET)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4, 7}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            timeout,
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert result.error == "purchase_unverified"
    assert result.attempted_slots == (4,)
    assert events == ["black_market.purchase_unverified"]
    assert SelectBlackMarketSlot(7) not in actions


def test_unexpected_branch_timeout_aborts_without_recovery_or_extra_taps():
    timeout = RuntimeWaitTimeout(
        after_sequence=3,
        timeout=5.0,
        last_snapshot=_snapshot(4),
    )
    result, actions, events, _ = _run(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(3, base=SCREEN_BLACK_MARKET)],
        [_snapshot(2, base=SCREEN_BLACK_MARKET, gold={0}), timeout],
    )

    assert result.status is FlowStatus.FAILED
    assert result.attempted_slots == (0,)
    assert actions == [OpenBlackMarket(), SelectBlackMarketSlot(0)]
    assert events == ["black_market.unexpected_state"]


def test_simultaneous_incompatible_purchase_overlays_abort_immediately():
    result, actions, events, _ = _run(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(3, base=SCREEN_BLACK_MARKET)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={0}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={
                    POPUP_PURCHASE_CONFIRMATION,
                    POPUP_INSUFFICIENT_GOLD,
                },
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert actions == [OpenBlackMarket(), SelectBlackMarketSlot(0)]
    assert events == ["black_market.unexpected_state"]


def test_invalid_smoke_limit_is_rejected_before_any_observation():
    observer = ScriptedObserver([], [])
    flow = BlackMarketFlow(observer, Actions(), Events())

    with pytest.raises(ValueError, match="max_slot_attempts"):
        flow.run(max_slot_attempts=-1)
