"""Transversal portal-obstruction recovery used on demand by verifiers.

The recovery owns the only portal-specific policy in the runtime: probe a
fresh frame with an explicitly intersecting failed signal or input target, tap the dismiss X
exactly through the normal action layer when the probe is CONFIRMED, observe
a fresh frame, verify disappearance boundedly, and hand the freshest snapshot
back so the caller re-evaluates its *original* condition. It never repeats
the caller's productive action and never treats INCONCLUSIVE/ABSENT as tap
permission.

``VerifiedTransition`` supplies the failed condition's declared geometry or
asks for an input conflict. Successful unaffected transitions never probe.
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
from bot.state import ResolutionStatus


# Physical GT, not the detector search ROI (docs/GAMEPLAY_GT.md).
PORTAL_OCCLUSION_ENVELOPE = (0.165, 0.105, 0.360, 0.260)

# Explicit physical BASEs represented by the current resolver. Technical
# screen.* names alone do not establish physical class. Craft's reader facts
# need no synthetic ResolvedState here.
_NON_BATTLE_BASES = frozenset({
    "screen.lobby", "screen.battle_mode_select", "screen.monster_wave",
    "screen.socket", "screen.treasure", "screen.combine", "screen.guild",
    "screen.pets_manage", "screen.pet_summon", "screen.pet_combine",
    "screen.world_boss",
})
_BASE_DETAILS = frozenset({
    "status.world_boss_daily_active", "status.monster_wave_daily_active",
    "status.pet_summon_daily_active", "status.pet_epic_available",
    "status.pet_epic_unavailable", "status.pet_premium_gold",
    "status.pet_premium_ticket_available", "status.guild_attendance_active",
    "status.guild_attendance_completed", "status.guild_attendance_daily_active",
    "mode.combine_fuse", "mode.combine_transmute",
    "panel.combine_awakened_transmute", "panel.combine_ethereal_random_part",
    "status.combine_ethereal_available", "status.combine_fuse_available",
    "status.combine_transmute_available",
})


def intersects_obstruction(*, regions=(), target=None):
    """Pure normalized geometry; no perception or input."""
    left, top, right, bottom = PORTAL_OCCLUSION_ENVELOPE
    if target is not None:
        x, y = target
        if left <= x <= right and top <= y <= bottom:
            return True
    return any(x1 < right and x2 > left and y1 < bottom and y2 > top
               for x1, y1, x2, y2 in regions)


def _compatible_surface(snapshot):
    state = snapshot.state
    if not set(state.overlays) <= _BASE_DETAILS:
        return False
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context in _NON_BATTLE_BASES
    )


@dataclass(frozen=True)
class ObstructionRecoveryPolicy:
    """Bounded dismissal budget and passive settle window for one attempt.

    ``settle_timeout`` is anchored in the live smoke of 2026-09-06: the frame
    ~2 s after an effective dismiss tap still classified CONFIRMED (fade),
    with absence confirmed later and no other input. The 5 s window keeps a
    ~2.5x margin over that measured lower bound; it performs zero input and
    exits early on ABSENT.
    """

    max_dismiss_attempts: int = 1
    settle_timeout: float = 5.0
    settle_poll_interval: float = 0.5

    def __post_init__(self) -> None:
        value = self.max_dismiss_attempts
        if isinstance(value, bool) or not isinstance(value, Integral) or value != 1:
            raise ValueError("max_dismiss_attempts must be exactly one")
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

    def input_conflicts(self, action):
        """Return the existing target only when it can be covered."""
        target_for = getattr(self.actions, "target_for", None)
        if not callable(target_for):
            return None
        # Swipes have no discrete tap target and are outside this recovery.
        from bot.semantic_actions import Swipe
        if isinstance(action, (Swipe, DismissPortalNotification)):
            return None
        try:
            target = target_for(action)
        except (TypeError, ValueError):
            # Preserve the executor's normal validation/failure reporting.
            return None
        return target if intersects_obstruction(target=target) else None

    def attempt(
        self,
        snapshot,
        expected: Callable[[object], bool],
        *,
        regions=(),
        target=None,
        monster_wave_entry_source=None,
        stages_entry_source=None,
    ):
        """Try to clear a confirmed portal; return freshest snapshot or None.

        A failed predicate must supply its necessary signal regions. Input
        conflicts supply the executor's actual target. No cause means no probe.
        UNKNOWN resolution never supplies the physical authorization. Failed
        signals within an established BASE can be recovered independently.
        Once input is attempted, failure to obtain a fresh frame raises rather
        than letting the caller reuse pre-cleanup evidence for another action.
        """

        if not callable(expected):
            raise ValueError("expected must be callable")
        if not intersects_obstruction(regions=regions, target=target):
            return None
        if target is None and expected(snapshot):
            return None
        # Narrow MW entry handoff: the caller supplies the verified source of
        # effective OpenMonsterWave, after normalizing all known entry modals.
        # This permits only causal cleanup, never generic input from UNKNOWN.
        entry_context = (
            monster_wave_entry_source is not None
            and _compatible_surface(monster_wave_entry_source)
            and monster_wave_entry_source.state.base_context == "screen.battle_mode_select"
            and snapshot.sequence > monster_wave_entry_source.sequence
            and snapshot.state.status is ResolutionStatus.UNKNOWN
            and not snapshot.state.overlays
            and target is None
        )
        # Acquired Stage Start guard → Socket/Combine: the portal may hide
        # their first base landmark. This handoff never replays Start or ad.
        stages_entry_context = (
            stages_entry_source is not None
            and stages_entry_source.state.base_context == "screen.stages"
            and set(stages_entry_source.state.overlays).intersection({
                "popup.socket_inventory_full", "popup.equipment_inventory_full"})
            and snapshot.sequence > stages_entry_source.sequence
            and snapshot.state.status is ResolutionStatus.UNKNOWN
            and not snapshot.state.overlays
            and target is None
        )
        if not _compatible_surface(snapshot) and not entry_context and not stages_entry_context:
            return None
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
            self._check_cancelled()
            latest, outcome = self._settle(fresh)
            self._check_cancelled()
            if outcome is PortalProbeOutcome.ABSENT:
                self._record("obstruction_recovery.cleared")
                return latest
            self._record("obstruction_recovery.not_cleared", outcome=outcome.value)
        raise RuntimeWaitTimeout(
            after_sequence=snapshot.sequence,
            timeout=self.policy.settle_timeout,
            last_snapshot=latest,
        )

    def _settle(self, snapshot):
        """Passively reprobe after a tap, bounded, without any input.

        Returns the freshest snapshot and its probe outcome. ABSENT ends the
        wait early. Persistence, INCONCLUSIVE or a stalled source cannot
        authorize another tap; the caller reports a technical failure.
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
            except RuntimeWaitCancelled:
                raise
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
