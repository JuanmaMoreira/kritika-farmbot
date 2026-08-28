import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import (
    BLACK_MARKET_GOLD_OBSERVATION,
    BLACK_MARKET_PURCHASED_OBSERVATION,
)
from bot.resolver import ContextResolver
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)


class Source:
    def __init__(self, sequences):
        self.sequences = list(sequences)
        self.index = 0

    def get_frame(self):
        index = min(self.index, len(self.sequences) - 1)
        sequence = self.sequences[index]
        self.index += 1
        return FrameSnapshot(
            image=np.zeros((72, 160, 3), dtype=np.uint8),
            timestamp=float(sequence),
            sequence=sequence,
        )


class Perception:
    def __init__(self, observations=()):
        self.observations = tuple(observations)

    def analyze(self, snapshot):
        return ObservationBatch(
            sequence=snapshot.sequence,
            timestamp=snapshot.timestamp,
            observations=self.observations,
        )


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


def _observer(sequences, observations=()):
    clock = Clock()
    return RuntimeObserver(
        Source(sequences),
        Perception(observations),
        ContextResolver(),
        poll_interval=0.1,
        clock=clock,
        sleeper=clock.sleep,
    )


def test_observe_keeps_state_facts_and_geometry_on_one_frame_identity():
    observations = (
        Observation(
            name=BLACK_MARKET_GOLD_OBSERVATION,
            confidence=1.0,
            source=ObservationSource.LOCAL_CV,
            value=2,
        ),
        Observation(
            name=BLACK_MARKET_PURCHASED_OBSERVATION,
            confidence=1.0,
            source=ObservationSource.LOCAL_CV,
            value=7,
        ),
    )

    snapshot = _observer([4], observations).observe()

    assert snapshot.sequence == 4
    assert snapshot.observations.sequence == snapshot.state.sequence == 4
    assert snapshot.facts.gold_slots == frozenset({2})
    assert snapshot.facts.purchased_slots == frozenset({7})
    assert (snapshot.geometry.width, snapshot.geometry.height) == (160, 72)


def test_wait_until_ignores_stale_snapshots_even_when_condition_is_true():
    observer = _observer([5, 5, 6])

    snapshot = observer.wait_until(
        lambda item: True,
        after_sequence=5,
        timeout=1.0,
    )

    assert snapshot.sequence == 6


def test_wait_until_returns_fresh_snapshot_that_satisfies_condition():
    observer = _observer([3, 4, 5])

    snapshot = observer.wait_until(
        lambda item: item.sequence >= 5,
        after_sequence=3,
        timeout=1.0,
    )

    assert snapshot.sequence == 5


def test_wait_until_times_out_without_accepting_stale_frame():
    observer = _observer([9])

    with pytest.raises(RuntimeWaitTimeout) as raised:
        observer.wait_until(
            lambda item: True,
            after_sequence=9,
            timeout=0.25,
        )

    assert raised.value.last_snapshot is None


def test_wait_until_can_abort_on_an_incompatible_fresh_snapshot():
    observer = _observer([10, 11])

    with pytest.raises(RuntimeWaitAborted) as raised:
        observer.wait_until(
            lambda item: False,
            abort_if=lambda item: item.sequence == 11,
            after_sequence=10,
            timeout=1.0,
        )

    assert raised.value.snapshot.sequence == 11


def test_wait_until_can_require_condition_stability_across_fresh_frames():
    observer = _observer([1, 2, 3, 4, 5])

    snapshot = observer.wait_until(
        lambda item: item.sequence >= 2,
        after_sequence=1,
        timeout=1.0,
        stable_for=2.0,
    )

    assert snapshot.sequence == 4


def test_wait_until_can_be_cancelled_before_observing_another_frame():
    observer = _observer([1])

    with pytest.raises(RuntimeWaitCancelled):
        observer.wait_until(
            lambda item: True,
            after_sequence=0,
            timeout=1.0,
            cancel_requested=lambda: True,
        )


def test_wait_until_stability_resets_when_condition_becomes_false():
    observer = _observer([1, 2, 3, 4, 5, 6])

    snapshot = observer.wait_until(
        lambda item: item.sequence not in {3},
        after_sequence=1,
        timeout=1.0,
        stable_for=2.0,
    )

    assert snapshot.sequence == 6
