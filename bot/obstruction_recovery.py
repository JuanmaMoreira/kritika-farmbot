"""Transversal portal-obstruction recovery used on demand by verifiers.

The recovery owns the only portal-specific policy in the runtime: probe a
fresh frame that already failed an expected condition, tap the dismiss X
exactly through the normal action layer when the probe is CONFIRMED, observe
a fresh frame, verify disappearance boundedly, and hand the freshest snapshot
back so the caller re-evaluates its *original* condition. It never repeats
the caller's productive action and never treats INCONCLUSIVE/ABSENT as tap
permission.

``VerifiedTransition`` stays generic: it only knows the ``attempt(snapshot,
expected)`` protocol, never Heaven/Hell details.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Callable

from bot.portal_notification import PortalNotificationProbe, PortalProbeOutcome
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import DismissPortalNotification


@dataclass(frozen=True)
class ObstructionRecoveryPolicy:
    """Bounded dismissal budget and passive settle window for one attempt.

    ``settle_timeout`` is anchored in the live smoke of 2026-09-06: the frame
    ~2 s after an effective dismiss tap still classified CONFIRMED (fade),
    with absence confirmed later and no other input. The 5 s window keeps a
    ~2.5x margin over that measured lower bound; it performs zero input and
    exits early on ABSENT.
    """

    max_dismiss_attempts: int = 2
    settle_timeout: float = 5.0
    settle_poll_interval: float = 0.5

    def __post_init__(self) -> None:
        value = self.max_dismiss_attempts
        if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
            raise ValueError("max_dismiss_attempts must be a positive integer")
        object.__setattr__(self, "max_dismiss_attempts", int(value))
        object.__setattr__(
            self,
            "settle_timeout",
            _positive_duration(self.settle_timeout, "settle_timeout"),
        )
        object.__setattr__(
            self,
            "settle_poll_interval",
            _positive_duration(
                self.settle_poll_interval, "settle_poll_interval"
            ),
        )


class PortalObstructionRecovery:
    """On-demand portal cleanup composing observer + actions + probe."""

    def __init__(
        self,
        observer,
        actions,
        probe: PortalNotificationProbe | None = None,
        *,
        policy: ObstructionRecoveryPolicy | None = None,
        events=None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)):
            raise ValueError("observer must provide observe()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        if probe is not None and not callable(getattr(probe, "probe", None)):
            raise ValueError("probe must provide probe(frame_image) or None")
        if policy is not None and not isinstance(
            policy, ObstructionRecoveryPolicy
        ):
            raise ValueError("policy must be ObstructionRecoveryPolicy or None")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable or None")
        if sleeper is not None and not callable(sleeper):
            raise ValueError("sleeper must be callable or None")
        if cancel_requested is not None and not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable or None")
        self.observer = observer
        self.actions = actions
        self.probe = probe or PortalNotificationProbe()
        self.policy = policy or ObstructionRecoveryPolicy()
        self.events = events
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self.cancel_requested = cancel_requested

    def attempt(
        self,
        snapshot,
        expected: Callable[[object], bool],
    ):
        """Try to clear a confirmed portal; return freshest snapshot or None.

        Returns None only when the initial probe does not confirm an obstruction.
        Once input is attempted, failure to obtain a fresh frame raises rather
        than letting the caller reuse pre-cleanup evidence for another action.
        """

        if not callable(expected):
            raise ValueError("expected must be callable")
        self._check_cancelled()
        try:
            initial = self.probe.probe(snapshot.frame.image)
        except Exception:
            return None
        if initial is not PortalProbeOutcome.CONFIRMED:
            return None
        self._record("obstruction_recovery.confirmed")
        latest = snapshot
        for _ in range(self.policy.max_dismiss_attempts):
            self._check_cancelled()
            try:
                self.actions.execute(
                    DismissPortalNotification(), latest.geometry
                )
            except Exception as error:
                self._record(
                    "obstruction_recovery.dismiss_failed",
                    error=f"{type(error).__name__}: {error}",
                )
                raise
            try:
                fresh = self.observer.observe()
            except Exception as error:
                self._record(
                    "obstruction_recovery.observe_failed",
                    error=f"{type(error).__name__}: {error}",
                )
                raise
            if fresh.sequence <= latest.sequence:
                self._record("obstruction_recovery.stale_frame")
                raise RuntimeWaitTimeout(
                    after_sequence=latest.sequence,
                    timeout=self.policy.settle_timeout,
                    last_snapshot=fresh,
                )
            latest, outcome = self._settle(fresh)
            if outcome is PortalProbeOutcome.ABSENT:
                self._record("obstruction_recovery.cleared")
                return latest
            if outcome is not PortalProbeOutcome.CONFIRMED:
                self._record("obstruction_recovery.inconclusive_after_dismiss")
                return latest
            self._record("obstruction_recovery.still_present")
        return latest

    def _settle(self, snapshot):
        """Passively reprobe after a tap, bounded, without any input.

        Returns the freshest snapshot and its probe outcome. Only a freshly
        probed CONFIRMED outcome authorizes the caller to spend another (at
        most one more) tap; ABSENT ends the wait early, while INCONCLUSIVE or
        a stalled source (no fresh frame) ends it without tap permission.
        """

        latest = snapshot
        try:
            outcome: PortalProbeOutcome | None = self.probe.probe(
                latest.frame.image
            )
        except Exception:
            outcome = PortalProbeOutcome.INCONCLUSIVE
        if outcome is PortalProbeOutcome.ABSENT:
            return latest, outcome
        deadline = self._clock() + self.policy.settle_timeout
        while True:
            remaining = deadline - self._clock()
            self._check_cancelled()
            if remaining <= 0:
                return latest, outcome
            self._sleeper(min(self.policy.settle_poll_interval, remaining))
            self._check_cancelled()
            try:
                fresh = self.observer.observe()
            except Exception:
                return latest, PortalProbeOutcome.INCONCLUSIVE
            if fresh.sequence <= latest.sequence:
                outcome = PortalProbeOutcome.INCONCLUSIVE
                continue
            latest = fresh
            try:
                outcome = self.probe.probe(latest.frame.image)
            except Exception:
                outcome = PortalProbeOutcome.INCONCLUSIVE
            if outcome is PortalProbeOutcome.ABSENT:
                return latest, outcome

    def _check_cancelled(self) -> None:
        if self.cancel_requested is not None and self.cancel_requested():
            raise RuntimeWaitCancelled("obstruction recovery cancelled")

    def _record(self, event: str, **fields: object) -> None:
        if self.events is None:
            return
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


__all__ = (
    "ObstructionRecoveryPolicy",
    "PortalObstructionRecovery",
)
