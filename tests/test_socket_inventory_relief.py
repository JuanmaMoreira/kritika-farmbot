from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    POPUP_SOCKET_ENHANCE_ALL,
    POPUP_SOCKET_NO_MATERIAL,
    POPUP_SOCKET_SELL,
    SCREEN_SOCKET,
    SCREEN_WORLD_BOSS,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception.socket import (
    SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
    SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
)
from bot.runtime_facts import (
    FactEvidence,
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    CancelSocketSell,
    ExitSocket,
    OpenSocketEquipmentHome,
    SelectSocketEnhanceGold,
    SelectSocketOpalSlot,
    SellSocketInBulk,
)
from bot.socket_inventory_relief import (
    SocketInventoryRelief,
    SocketReliefOutcome,
    SocketReturnPlan,
    SocketStrategyOutcome,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.tap_through_animation import TapThroughOutcome, TapThroughResult
from bot.verified_transition import (
    VerifiedTransitionOutcome,
    VerifiedTransitionResult,
)


def snapshot(sequence, *, base=None, overlays=(), equipment=False, slots=(), tappable=False):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    observations = []
    if equipment:
        observations.append(
            Observation(
                LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
                1.0,
                ObservationSource.LOCAL_CV,
            )
        )
    observations.extend(
        Observation(
            SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
            1.0,
            ObservationSource.LOCAL_CV,
            value=slot,
        )
        for slot in slots
    )
    if tappable:
        observations.append(
            Observation(
                SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
                1.0,
                ObservationSource.LOCAL_CV,
            )
        )
    status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), tuple(observations)),
        ResolvedState(status, sequence, float(sequence), base_context=base, overlays=overlays),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def confirmed_level(value, sequence=50):
    evidence = FactEvidence(sequence, float(sequence), str(value), 0.99)
    return FactReadResult(
        FactReadStatus.CONFIRMED,
        RuntimeFact(
            "item.socket.sell_level",
            value,
            0.99,
            FactQuality.CONSENSUS,
            ObservationSource.OCR,
            SCREEN_SOCKET,
            (evidence,),
        ),
        (evidence,),
    )


class Observer:
    def __init__(self, initial, waits=()):
        self.initial = initial
        self.waits = list(waits)

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
        value = self.waits.pop(0)
        assert condition(value)
        return value


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append(action)


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


class Facts:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def read_socket_sell_item_level(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


class Transitions:
    def __init__(self, finals):
        self.finals = list(finals)
        self.calls = []

    def execute(self, name, action, before, **kwargs):
        self.calls.append((name, action, before, kwargs))
        assert kwargs["precondition"](before)
        final = self.finals.pop(0)
        succeeded = final is not None and kwargs["expected"](final)
        return VerifiedTransitionResult(
            name,
            (
                VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
                if succeeded
                else VerifiedTransitionOutcome.TIMEOUT
            ),
            1,
            0,
            final or before,
            None if succeeded else "scripted failure",
        )


class TapThrough:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def run(self, initial, **kwargs):
        self.calls.append((initial, kwargs))
        return self.result


def build(initial, transitions, *, waits=(), facts=(), tap_result=None):
    observer = Observer(initial, waits)
    actions = Actions()
    events = Events()
    fact_reader = Facts(facts)
    transition_driver = Transitions(transitions)
    tap = TapThrough(tap_result)
    operation = SocketInventoryRelief(
        observer,
        actions,
        fact_reader,
        events,
        verified_transition=transition_driver,
        tap_through=tap,
        stable_for=0,
    )
    return operation, observer, actions, fact_reader, events, transition_driver, tap


def plan():
    return SocketReturnPlan(ExitSocket(), SCREEN_WORLD_BOSS)


def no_material_prefix(start=2):
    return [
        snapshot(start, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_ENHANCE_ALL,)),
        snapshot(
            start + 1,
            base=SCREEN_SOCKET,
            overlays=(POPUP_SOCKET_ENHANCE_ALL, POPUP_SOCKET_NO_MATERIAL),
        ),
        snapshot(start + 2, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_ENHANCE_ALL,)),
        snapshot(start + 3, base=SCREEN_SOCKET),
    ]


def test_precondition_requires_exact_fresh_socket_and_cancellation_is_distinct():
    wrong, *_ = build(snapshot(1, base=SCREEN_WORLD_BOSS), [])
    cancelled, *_ = build(snapshot(1, base=SCREEN_SOCKET), [])

    wrong_result = wrong.run(plan())
    cancelled_result = cancelled.run(plan(), lambda: True)

    assert wrong_result.outcome is SocketReliefOutcome.FAILED
    assert cancelled_result.outcome is SocketReliefOutcome.CANCELLED


def test_enhance_gold_effect_short_circuits_sell_and_returns_verified():
    initial = snapshot(1, base=SCREEN_SOCKET)
    animation = snapshot(3, tappable=True)
    completed = snapshot(4, base=SCREEN_SOCKET)
    tap_result = TapThroughResult(TapThroughOutcome.COMPLETED, 3, completed)
    operation, _, actions, facts, _, transitions, tap = build(
        initial,
        [
            snapshot(2, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_ENHANCE_ALL,)),
            animation,
            snapshot(5, base=SCREEN_WORLD_BOSS),
        ],
        tap_result=tap_result,
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.RELIEVED
    assert result.enhance is SocketStrategyOutcome.EFFECT
    assert result.sell is SocketStrategyOutcome.NOT_RUN
    assert result.animation_taps == 3
    assert facts.calls == []
    assert len(tap.calls) == 1
    assert any(isinstance(call[1], SelectSocketEnhanceGold) for call in transitions.calls)
    assert not any("Karat" in type(call[1]).__name__ for call in transitions.calls)
    assert actions.calls == []


def test_no_material_closes_modal_then_zero_candidates_returns_no_relief():
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True)
    operation, *_ = build(
        initial,
        [*no_material_prefix(), equipment, snapshot(7, base=SCREEN_WORLD_BOSS)],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.enhance is SocketStrategyOutcome.NO_EFFECT
    assert result.sell is SocketStrategyOutcome.NO_EFFECT


def test_enhance_timeout_without_explicit_outcome_fails_and_never_sells():
    initial = snapshot(1, base=SCREEN_SOCKET)
    operation, _, _, facts, _, transitions, _ = build(
        initial,
        [
            snapshot(2, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_ENHANCE_ALL,)),
            None,
        ],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.FAILED
    assert facts.calls == []
    assert not any(isinstance(call[1], OpenSocketEquipmentHome) for call in transitions.calls)


def test_red_candidate_level_zero_uses_bulk_and_requires_slot_disappearance():
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    selected = snapshot(7, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    popup = snapshot(8, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,), equipment=True, slots=(4,))
    sold = snapshot(9, base=SCREEN_SOCKET, equipment=True)
    operation, _, actions, _, events, transitions, _ = build(
        initial,
        [
            *no_material_prefix(),
            equipment,
            popup,
            sold,
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        waits=[selected],
        facts=[confirmed_level(0)],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.RELIEVED
    assert result.sell is SocketStrategyOutcome.EFFECT
    assert [type(item) for item in actions.calls] == [SelectSocketOpalSlot]
    assert any(isinstance(call[1], SellSocketInBulk) for call in transitions.calls)
    assert not any(type(call[1]).__name__ == "SellSocket" for call in transitions.calls)
    assert any(event == "socket_relief.sell_bulk_verified" for event, _ in events.records)

    bulk_call = next(
        call for call in transitions.calls if isinstance(call[1], SellSocketInBulk)
    )
    passive_transit = snapshot(20, base=SCREEN_SOCKET)
    assert bulk_call[3]["retryable_from"](passive_transit) is False
    assert bulk_call[3]["abort_if"](passive_transit) is False
    assert bulk_call[3]["abort_if"](
        snapshot(21, base=SCREEN_WORLD_BOSS)
    ) is True


@pytest.mark.parametrize(
    "fact_result",
    [
        confirmed_level(10),
        FactReadResult(FactReadStatus.UNREADABLE, detail="unreadable"),
        FactReadResult(FactReadStatus.UNCERTAIN, detail="uncertain"),
    ],
)
def test_nonzero_or_unconfirmed_level_cancels_and_never_bulk_sells(fact_result):
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    selected = snapshot(7, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    popup = snapshot(8, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,), equipment=True)
    returned = snapshot(9, base=SCREEN_SOCKET, equipment=True)
    operation, _, _, _, _, transitions, _ = build(
        initial,
        [
            *no_material_prefix(),
            equipment,
            popup,
            returned,
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        waits=[selected],
        facts=[fact_result],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.NO_RELIEF_AVAILABLE
    assert any(isinstance(call[1], CancelSocketSell) for call in transitions.calls)
    assert not any(isinstance(call[1], SellSocketInBulk) for call in transitions.calls)


def test_multiple_candidates_can_skip_unsafe_then_sell_next_safe_one():
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True, slots=(4, 5))
    first_selected = snapshot(7, base=SCREEN_SOCKET, equipment=True, slots=(4, 5))
    first_popup = snapshot(8, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,))
    after_cancel = snapshot(9, base=SCREEN_SOCKET, equipment=True, slots=(4, 5))
    second_selected = snapshot(10, base=SCREEN_SOCKET, equipment=True, slots=(4, 5))
    second_popup = snapshot(11, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,))
    sold = snapshot(12, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    operation, _, actions, _, _, transitions, _ = build(
        initial,
        [
            *no_material_prefix(),
            equipment,
            first_popup,
            after_cancel,
            second_popup,
            sold,
            snapshot(13, base=SCREEN_WORLD_BOSS),
        ],
        waits=[first_selected, second_selected],
        facts=[confirmed_level(10), confirmed_level(0, 60)],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.RELIEVED
    assert [item.slot_index for item in actions.calls] == [4, 5]
    assert sum(isinstance(call[1], SellSocketInBulk) for call in transitions.calls) == 1


def test_bulk_popup_disappearing_without_slot_change_is_failure():
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    selected = snapshot(7, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    popup = snapshot(8, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,))
    unchanged = snapshot(9, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    operation, *_ = build(
        initial,
        [*no_material_prefix(), equipment, popup, unchanged],
        waits=[selected],
        facts=[confirmed_level(0)],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.FAILED
    assert result.sell is SocketStrategyOutcome.FAILED


def test_verified_effect_still_fails_if_return_plan_does_not_restore_expected_state():
    initial = snapshot(1, base=SCREEN_SOCKET)
    animation = snapshot(3, tappable=True)
    completed = snapshot(4, base=SCREEN_SOCKET)
    operation, *_ = build(
        initial,
        [
            snapshot(2, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_ENHANCE_ALL,)),
            animation,
            snapshot(5, base=SCREEN_SOCKET),
        ],
        tap_result=TapThroughResult(TapThroughOutcome.COMPLETED, 1, completed),
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.FAILED
    assert result.enhance is SocketStrategyOutcome.EFFECT


def test_fact_cancellation_uses_safe_cancel_cleanup_and_propagates_cancelled():
    initial = snapshot(1, base=SCREEN_SOCKET)
    equipment = snapshot(6, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    selected = snapshot(7, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    popup = snapshot(8, base=SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,))
    cleaned = snapshot(9, base=SCREEN_SOCKET, equipment=True, slots=(4,))
    operation, _, _, _, _, transitions, _ = build(
        initial,
        [*no_material_prefix(), equipment, popup, cleaned],
        waits=[selected],
        facts=[FactReadResult(FactReadStatus.CANCELLED)],
    )

    result = operation.run(plan())

    assert result.outcome is SocketReliefOutcome.CANCELLED
    assert any(isinstance(call[1], CancelSocketSell) for call in transitions.calls)
