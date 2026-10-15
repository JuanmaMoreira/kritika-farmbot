"""Reusable verified operation for bounded discrete UI transitions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
import time
from enum import Enum
from numbers import Integral, Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor, DispatchReceipt, DispatchState
from bot.event_log import EventSink
from bot.event_context import operation_scope, event_scope, event_context
from bot.failure_cause import FailureCause
from bot.geometry import RelativeRegion
from bot.runtime_observer import (
    RuntimeEvidenceRequirements,
    RuntimeEvidenceRejected,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import SemanticAction
from bot.operation_control import (
    OperationControl, OperationBudgetExpired, check_operation, current_control,
    control_scope, operation_phase,
)

EvidenceRegions = tuple[RelativeRegion, ...] | Callable[[RuntimeSnapshot], tuple[RelativeRegion, ...]]


class VerifiedTransitionOutcome(str, Enum):
    SUCCESS_FIRST_ATTEMPT = "success_first_attempt"
    SUCCESS_AFTER_GRACE = "success_after_grace"
    SUCCESS_AFTER_RETRY = "success_after_retry"
    SUCCESS_AFTER_OBSTRUCTION_RECOVERY = "success_after_obstruction_recovery"
    PRECONDITION_REJECTED = "precondition_rejected"
    RETRY_GUARD_REJECTED = "retry_guard_rejected"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    UNEXPECTED_STATE = "unexpected_state"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True)
class VerifiedTransitionPolicy:
    """Small timing and attempt policy for one kind of transition."""

    normal_timeout: float = 6.0
    grace_timeout: float = 2.0
    retry_guard_timeout: float = 0.0
    max_attempts: int = 1
    total_timeout: float | None = None
    observation_timeout: float | None = None
    dispatch_timeout: float | None = None
    recovery_timeout: float | None = None

    def __post_init__(self) -> None:
        for name in ("total_timeout", "observation_timeout", "dispatch_timeout", "recovery_timeout"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, _positive_duration(getattr(self, name), name))
        object.__setattr__(
            self,
            "normal_timeout",
            _positive_duration(self.normal_timeout, "normal_timeout"),
        )
        object.__setattr__(
            self,
            "grace_timeout",
            _positive_duration(self.grace_timeout, "grace_timeout"),
        )
        object.__setattr__(
            self,
            "retry_guard_timeout",
            _non_negative_duration(
                self.retry_guard_timeout, "retry_guard_timeout"
            ),
        )
        object.__setattr__(
            self,
            "max_attempts",
            _positive_integer(self.max_attempts, "max_attempts"),
        )


@dataclass(frozen=True)
class VerifiedTransitionResult:
    name: str
    outcome: VerifiedTransitionOutcome
    attempt_count: int
    grace_wait_count: int
    final_snapshot: RuntimeSnapshot
    error: str | None = None
    elapsed: float | None = field(default=None, kw_only=True)
    operation_id: str | None = field(default=None, kw_only=True)
    failure: FailureCause | None = field(default=None, kw_only=True)
    action_source_snapshot: RuntimeSnapshot | None = field(default=None, kw_only=True)
    recovery_after_action: bool = field(default=False, kw_only=True)
    dispatch_receipts: tuple[DispatchReceipt, ...] = field(default=(), kw_only=True)
    effect_accredited: bool = field(default=False, kw_only=True)
    ready: bool | None = field(default=None, kw_only=True)
    termination_reason: str | None = field(default=None, kw_only=True)
    progress_snapshot: RuntimeSnapshot | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.outcome, VerifiedTransitionOutcome):
            raise ValueError("outcome must be VerifiedTransitionOutcome")
        object.__setattr__(
            self,
            "attempt_count",
            _non_negative_integer(self.attempt_count, "attempt_count"),
        )
        object.__setattr__(
            self,
            "grace_wait_count",
            _non_negative_integer(self.grace_wait_count, "grace_wait_count"),
        )
        if not isinstance(self.final_snapshot, RuntimeSnapshot):
            raise ValueError("final_snapshot must be RuntimeSnapshot")
        if self.action_source_snapshot is not None and not isinstance(
            self.action_source_snapshot, RuntimeSnapshot
        ):
            raise ValueError("action_source_snapshot must be RuntimeSnapshot or None")

    @property
    def succeeded(self) -> bool:
        return self.outcome in {
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE,
            VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY,
            VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
        }


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class ObstructionRecovery(Protocol):
    """Generic cleanup for a declared signal or target conflict.

    The protocol is intentionally free of any overlay-specific vocabulary:
    it receives the fresh snapshot and the caller's causal geometry and
    returns a fresher snapshot when it performed >= 1 cleanup tap, or None
    when it performed no tap. The caller re-evaluates its original condition
    and never repeats its productive action just because cleanup ran.
    """

    def attempt(
        self,
        snapshot: RuntimeSnapshot,
        expected: Callable[[RuntimeSnapshot], bool],
        *,
        regions: tuple = (),
        target=None,
        evidence: RuntimeEvidenceRequirements | None = None,
    ) -> RuntimeSnapshot | None: ...

    def input_conflicts(self, action: SemanticAction): ...


@dataclass
class _TransitionEvidence:
    requirements: RuntimeEvidenceRequirements | None
    latest: RuntimeSnapshot
    receipts: list = field(default_factory=list)
    captured_after: float | None = None
    effect_accredited: bool = False
    progress_snapshot: RuntimeSnapshot | None = None
    action_source_snapshot: RuntimeSnapshot | None = None
    recovery_after_action: bool = False

    def current_requirements(self):
        if self.requirements is None or self.captured_after is None:
            return self.requirements
        return replace(self.requirements, captured_after=max(
            self.captured_after, self.requirements.captured_after or 0,
        ))

    def valid(self, snapshot):
        requirements = self.current_requirements()
        return requirements is None or requirements.accepts(snapshot, current_control().clock())

    def require(self, snapshot):
        check_operation()
        self.latest = snapshot
        if not self.valid(snapshot):
            raise RuntimeEvidenceRejected("runtime_evidence_rejected")


class VerifiedTransition:
    """Execute an action and verify its postcondition with guarded retries."""

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink | None = None,
        obstruction_recovery: ObstructionRecovery | None = None,
        *,
        metrics_clock: Callable[[], float] = time.perf_counter,
        clock: Callable[[], float] = time.monotonic,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        if obstruction_recovery is not None and not callable(
            getattr(obstruction_recovery, "attempt", None)
        ):
            raise ValueError("obstruction_recovery must provide attempt() or None")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.obstruction_recovery = obstruction_recovery
        self._metrics_clock = metrics_clock
        self._clock = clock
        self.cancel_requested = cancel_requested

    def _metrics_now(self):
        try:
            return self._metrics_clock()
        except Exception:
            return 0.0

    def input_conflicts(self, action):
        """Pure target check supplied by the configured obstruction owner."""
        check = getattr(self.obstruction_recovery, "input_conflicts", None)
        return check(action) if callable(check) else None

    def recover_input(self, name, action, before, precondition, on_recovery=None, *, evidence=None):
        control = current_control() or OperationControl(
            cancel_requested=self.cancel_requested, clock=self._clock,
        )
        with control_scope(control):
            return self._recover_input(name, action, before, precondition, on_recovery, evidence=evidence)

    def _recover_input(self, name, action, before, precondition, on_recovery=None, *, evidence=None):
        """Prepare an intersecting input; its owner must revalidate the guard.

        Direct operations retain their existing wait/cancellation contracts.
        No target conflict means no observation or probe.
        """
        check_operation()
        target = self.input_conflicts(action)
        check_operation()
        if target is None or precondition is None:
            return None
        return self._try_recover(before, precondition, name, on_recovery, target=target, evidence=evidence)

    def execute(
        self,
        name: str,
        action: SemanticAction,
        before: RuntimeSnapshot,
        *,
        expected: Callable[[RuntimeSnapshot], bool],
        policy: VerifiedTransitionPolicy,
        precondition: Callable[[RuntimeSnapshot], bool] | None = None,
        retryable_from: Callable[[RuntimeSnapshot], bool] | None = None,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
        on_recovery: Callable[[], None] | None = None,
        precondition_regions: EvidenceRegions = (),
        expected_regions: EvidenceRegions = (),
        cancel_requested: Callable[[], bool] | None = None,
        evidence: RuntimeEvidenceRequirements | None = None,
        budget: OperationControl | None = None,
        effect_observed: Callable[[RuntimeSnapshot], bool] | None = None,
        progress_observed: Callable[[RuntimeSnapshot], bool] | None = None,
    ) -> VerifiedTransitionResult:
        if not isinstance(policy, VerifiedTransitionPolicy):
            raise ValueError("policy must be VerifiedTransitionPolicy")
        if not isinstance(before, RuntimeSnapshot):
            raise ValueError("before must be RuntimeSnapshot")
        if not callable(expected):
            raise ValueError("expected must be callable")
        if evidence is not None and not isinstance(evidence, RuntimeEvidenceRequirements):
            raise ValueError("evidence must be RuntimeEvidenceRequirements or None")
        for predicate in (cancel_requested, effect_observed, progress_observed, precondition, retryable_from, abort_if):
            if predicate is not None and not callable(predicate):
                raise ValueError("optional callbacks must be callable")
        if budget is not None and not isinstance(budget, OperationControl):
            raise ValueError("budget must be OperationControl or None")
        parent = budget or current_control()
        clock = parent.clock if parent is not None else self._clock
        control = OperationControl(
            cancel_requested=cancel_requested if cancel_requested is not None else self.cancel_requested,
            deadline=clock() + policy.total_timeout if policy.total_timeout is not None else None,
            observation_timeout=policy.observation_timeout,
            dispatch_timeout=policy.dispatch_timeout,
            recovery_timeout=policy.recovery_timeout, clock=clock, parent=parent,
        )
        if evidence is not None and evidence.source_id is None and before.frame.source_id is not None:
            evidence = replace(evidence, source_id=before.frame.source_id)
        state = _TransitionEvidence(evidence, before)

        def checked(predicate, *, postcondition=False):
            if predicate is None:
                return None
            def evaluate(snapshot):
                check_operation()
                state.latest = snapshot
                if not state.valid(snapshot):
                    return False
                with operation_phase("observation"):
                    if postcondition:
                        if effect_observed is not None:
                            effect = effect_observed(snapshot)
                            check_operation()
                            if effect and state.valid(snapshot):
                                state.effect_accredited = True
                        if progress_observed is not None:
                            if not state.valid(snapshot):
                                return False
                            progress_seen = progress_observed(snapshot)
                            check_operation()
                            if progress_seen and state.valid(snapshot):
                                state.progress_snapshot = snapshot
                        if not state.valid(snapshot):
                            return False
                    matched = predicate(snapshot)
                    check_operation()
                    valid = state.valid(snapshot)
                    return bool(matched and valid)
            return evaluate

        with operation_scope(name) as context, control_scope(control):
            started = self._metrics_now()
            progress = {"attempt": 0, "grace_count": 0}
            try:
                result = self._execute(
                    name, action, before, expected=checked(expected, postcondition=True), policy=policy,
                    precondition=checked(precondition), retryable_from=checked(retryable_from),
                    abort_if=checked(abort_if), stable_for=stable_for,
                    on_recovery=on_recovery, _progress=progress,
                    precondition_regions=precondition_regions,
                    expected_regions=expected_regions, _state=state,
                )
            except (OperationBudgetExpired, RuntimeEvidenceRejected) as error:
                receipt = getattr(error, "dispatch_receipt", None)
                if receipt is not None and receipt not in state.receipts:
                    state.receipts.append(receipt)
                result = self._result(
                    name, VerifiedTransitionOutcome.TIMEOUT,
                    progress["attempt"], progress["grace_count"], state.latest, str(error),
                    action_source_snapshot=state.action_source_snapshot,
                    recovery_after_action=state.recovery_after_action,
                )
            except BaseException as error:
                receipt = getattr(error, "dispatch_receipt", None)
                if receipt is not None and receipt not in state.receipts:
                    state.receipts.append(receipt)
                error.dispatch_receipts = tuple(state.receipts)
                error.effect_accredited = state.effect_accredited
                error.progress_snapshot = state.progress_snapshot
                failure = getattr(error, "failure", None) or FailureCause.from_error(
                    error, kind="exception",
                )
                self._record(
                    "transition.completed", transition=name,
                    outcome="cancelled" if isinstance(error, RuntimeWaitCancelled) else "failed",
                    elapsed=max(0.0, self._metrics_now() - started),
                    **progress,
                    before_sequence=getattr(before, "sequence", None),
                    error=f"{type(error).__name__}: {error}", failure=failure.payload(),
                    dispatch_receipts=[r.__dict__ for r in state.receipts],
                    effect_accredited=state.effect_accredited,
                )
                raise
            result = replace(
                result, elapsed=max(0.0, self._metrics_now() - started),
                operation_id=context["operation_id"],
                dispatch_receipts=tuple(state.receipts),
                effect_accredited=state.effect_accredited or (effect_observed is None and result.succeeded),
                ready=result.succeeded,
                termination_reason=result.error or result.outcome.value,
                progress_snapshot=state.progress_snapshot,
            )
            self._record(
                "transition.completed", transition=name,
                attempt=result.attempt_count, grace_count=result.grace_wait_count,
                outcome=result.outcome.value, error=result.error,
                elapsed=result.elapsed, before_sequence=before.sequence,
                final_sequence=result.final_snapshot.sequence,
                failure=result.failure.payload() if result.failure else None,
                dispatch_receipts=[r.__dict__ for r in state.receipts],
                effect_accredited=result.effect_accredited, ready=result.ready,
                termination_reason=result.termination_reason,
            )
            return result

    def _execute(
        self,
        name: str,
        action: SemanticAction,
        before: RuntimeSnapshot,
        *,
        expected: Callable[[RuntimeSnapshot], bool],
        policy: VerifiedTransitionPolicy,
        precondition: Callable[[RuntimeSnapshot], bool] | None = None,
        retryable_from: Callable[[RuntimeSnapshot], bool] | None = None,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
        on_recovery: Callable[[], None] | None = None,
        precondition_regions: EvidenceRegions = (),
        expected_regions: EvidenceRegions = (),
        _progress: dict,
        _state: _TransitionEvidence,
    ) -> VerifiedTransitionResult:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(before, RuntimeSnapshot):
            raise ValueError("before must be RuntimeSnapshot")
        if not isinstance(policy, VerifiedTransitionPolicy):
            raise ValueError("policy must be VerifiedTransitionPolicy")
        if not callable(expected):
            raise ValueError("expected must be callable")
        for predicate_name, predicate in (
            ("precondition", precondition),
            ("retryable_from", retryable_from),
            ("abort_if", abort_if),
        ):
            if predicate is not None and not callable(predicate):
                raise ValueError(f"{predicate_name} must be callable or None")
        stability = _non_negative_duration(stable_for, "stable_for")
        if on_recovery is not None and not callable(on_recovery):
            raise ValueError("on_recovery must be callable or None")

        check_operation()
        _state.require(before)

        def wait(*args, **kwargs):
            return self._wait(*args, evidence=_state.current_requirements(), **kwargs)

        def recover(snapshot, *args, **kwargs):
            _state.require(snapshot)
            if self.obstruction_recovery is not None and _state.action_source_snapshot is not None:
                # A cut during cleanup cannot certify a pristine handoff.
                _state.recovery_after_action = True
            result = self._try_recover(snapshot, *args, evidence=_state.current_requirements(), **kwargs)
            if result is not None:
                _state.require(result)
            return result

        def observe():
            with operation_phase("observation"):
                snapshot = self.observer.observe()
                _state.require(snapshot)
                return snapshot

        action_source_snapshot: RuntimeSnapshot | None = None
        recovery_after_action = False

        def finish(*args, **kwargs):
            return self._result(
                *args, action_source_snapshot=action_source_snapshot,
                recovery_after_action=recovery_after_action, **kwargs
            )

        def finish_late_success(outcome, attempt, grace_count, snapshot):
            # A single late observation (including cleanup/retry-guard output)
            # does not prove the caller's requested temporal stability.
            if stability > 0:
                settled = wait(
                    expected,
                    after_sequence=snapshot.sequence,
                    timeout=policy.normal_timeout,
                    abort_if=abort_if,
                    stable_for=stability,
                )
                if isinstance(settled, RuntimeWaitAborted):
                    return finish(
                        name, VerifiedTransitionOutcome.UNEXPECTED_STATE,
                        attempt, grace_count, settled.snapshot, str(settled),
                    )
                if isinstance(settled, RuntimeWaitTimeout):
                    return finish(
                        name, VerifiedTransitionOutcome.TIMEOUT,
                        attempt, grace_count, settled.last_snapshot or snapshot,
                        "late_expected_state_not_stable",
                    )
                snapshot = settled
            return finish(name, outcome, attempt, grace_count, snapshot)

        def finish_aborted(wait, attempt, grace_count):
            nonlocal recovery_after_action
            # A declared missing signal can explain an abort as well as a
            # timeout. Without that declaration preserve the original abort.
            snapshot = wait.snapshot
            if expected_regions:
                recovered = recover(
                    snapshot, expected, name, on_recovery, regions=expected_regions,
                )
                if recovered is not None:
                    recovery_after_action = True
                    snapshot = recovered
                    if expected(snapshot):
                        return finish_late_success(
                            VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
                            attempt, grace_count, snapshot,
                        )
            return finish(
                name, VerifiedTransitionOutcome.UNEXPECTED_STATE,
                attempt, grace_count, snapshot, str(wait),
            )

        self._record(
            "transition.started",
            transition=name,
            attempt=1,
            nominal_timeout=policy.normal_timeout,
            grace=policy.grace_timeout,
            max_attempts=policy.max_attempts,
        )
        if precondition is not None and not precondition(before):
            recovered = recover(
                before, precondition, name, on_recovery, regions=precondition_regions,
            )
            if recovered is not None and precondition(recovered):
                self._record(
                    "transition.obstruction_recovered",
                    transition=name,
                    phase="precondition",
                )
                current = recovered
            else:
                return finish(
                    name,
                    VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                    0,
                    0,
                    recovered if recovered is not None else before,
                    "precondition_rejected",
                )

        else:
            current = before
        grace_wait_count = 0
        for attempt in range(1, policy.max_attempts + 1):
            check_operation()
            if _state.effect_accredited:
                return finish(name, VerifiedTransitionOutcome.TIMEOUT, attempt - 1,
                              grace_wait_count, current, "effect_accredited_not_ready")
            guard = precondition if attempt == 1 else retryable_from
            _state.require(current)
            recovered = self.recover_input(
                name, action, current, guard, on_recovery,
                evidence=_state.current_requirements(),
            )
            check_operation()
            if recovered is not None:
                _state.require(recovered)
                recovery_after_action = action_source_snapshot is not None
                if (not guard(recovered) or
                        (abort_if is not None and abort_if(recovered))):
                    return finish(
                        name, VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                        attempt - 1, grace_wait_count, recovered,
                        "precondition_rejected_after_recovery",
                    )
                current = recovered
            try:
                _state.require(current)
                _progress["attempt"] = attempt
                with event_scope(attempt_index=attempt), operation_phase("dispatch"):
                    try:
                        _state.action_source_snapshot = None
                        if isinstance(self.actions, ActionExecutor):
                            execution = self.actions.execute(
                                action, current.geometry, events=self.events,
                                source_sequence=current.sequence,
                                before_dispatch=(lambda: _state.require(current)) if _state.requirements is not None else None,
                            )
                        else:
                            execution = self.actions.execute(action, current.geometry)
                    except BaseException as error:
                        receipt = getattr(error, "dispatch_receipt", None) or DispatchReceipt(
                            DispatchState.UNCERTAIN, operation_id=event_context()["operation_id"],
                            attempt_index=attempt,
                        )
                        _state.receipts.append(receipt)
                        raise
                    receipt = getattr(execution, "dispatch", None) or DispatchReceipt(
                        DispatchState.UNCERTAIN, operation_id=event_context()["operation_id"],
                        attempt_index=attempt, completed_at=current_control().clock(),
                    )
                    _state.receipts.append(receipt)
                    _state.action_source_snapshot = current
                    check_operation()
                _state.captured_after = current_control().clock()
                action_source_snapshot = current
            except (KeyboardInterrupt, SystemExit, RuntimeWaitCancelled, OperationBudgetExpired, RuntimeEvidenceRejected):
                raise
            except Exception as error:
                check_operation()
                # A partly completed executor call cannot certify this input.
                action_source_snapshot = None
                return finish(
                    name,
                    VerifiedTransitionOutcome.FAILED,
                    attempt,
                    grace_wait_count,
                    current,
                    f"{type(error).__name__}: {error}",
                    failure=FailureCause.from_error(error, kind="exception", sequence=current.sequence),
                )

            normal = wait(
                expected,
                after_sequence=current.sequence,
                timeout=policy.normal_timeout,
                abort_if=abort_if,
                stable_for=stability,
            )
            if isinstance(normal, RuntimeSnapshot):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return finish(
                    name,
                    outcome,
                    attempt,
                    grace_wait_count,
                    normal,
                )
            if isinstance(normal, RuntimeWaitAborted):
                return finish_aborted(normal, attempt, grace_wait_count)

            self._record(
                "transition.nominal_timeout",
                transition=name,
                attempt=attempt,
                nominal_timeout=policy.normal_timeout,
            )
            grace_wait_count += 1
            _progress["grace_count"] = grace_wait_count
            self._record(
                "transition.grace_started",
                transition=name,
                attempt=attempt,
                grace=policy.grace_timeout,
            )
            grace_anchor = normal.last_snapshot or current
            grace = wait(
                expected,
                after_sequence=grace_anchor.sequence,
                timeout=policy.grace_timeout,
                abort_if=abort_if,
                stable_for=stability,
            )
            if isinstance(grace, RuntimeSnapshot):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return finish(
                    name,
                    outcome,
                    attempt,
                    grace_wait_count,
                    grace,
                )
            if isinstance(grace, RuntimeWaitAborted):
                return finish_aborted(grace, attempt, grace_wait_count)

            try:
                observed = observe()
            except (KeyboardInterrupt, SystemExit, RuntimeWaitCancelled, OperationBudgetExpired, RuntimeEvidenceRejected):
                raise
            except Exception as error:
                check_operation()
                return finish(
                    name,
                    VerifiedTransitionOutcome.FAILED,
                    attempt,
                    grace_wait_count,
                    grace.last_snapshot or grace_anchor,
                    f"{type(error).__name__}: {error}",
                    failure=FailureCause.from_error(error, kind="exception", sequence=(grace.last_snapshot or grace_anchor).sequence),
                )
            latest_wait = grace.last_snapshot or grace_anchor
            if observed.sequence <= latest_wait.sequence:
                # observe() reads the latest stream frame; it need not advance
                # immediately after the wait's final poll. Acquire evidence,
                # without input, before deciding whether a retry is safe.
                fresh = wait(lambda item: True,
                                   after_sequence=latest_wait.sequence,
                                   timeout=policy.grace_timeout,
                                   abort_if=None, stable_for=0.0)
                if isinstance(fresh, RuntimeSnapshot):
                    observed = fresh
            if observed.sequence <= latest_wait.sequence:
                return finish(
                    name,
                    VerifiedTransitionOutcome.TIMEOUT,
                    attempt,
                    grace_wait_count,
                    observed,
                    "retry_state_not_fresh",
                )
            if expected(observed):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return finish_late_success(outcome, attempt, grace_wait_count, observed)
            if abort_if is not None and abort_if(observed):
                return finish(
                    name,
                    VerifiedTransitionOutcome.UNEXPECTED_STATE,
                    attempt,
                    grace_wait_count,
                    observed,
                    "unexpected_state_after_grace",
                )
            recovered = recover(
                observed, expected, name, on_recovery, regions=expected_regions,
            )
            if recovered is not None:
                recovery_after_action = True
                if expected(recovered):
                    self._record(
                        "transition.obstruction_recovered",
                        transition=name,
                        phase="postcondition",
                    )
                    return finish_late_success(
                        VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
                        attempt,
                        grace_wait_count,
                        recovered,
                    )
                observed = recovered
                if abort_if is not None and abort_if(observed):
                    return finish(
                        name,
                        VerifiedTransitionOutcome.UNEXPECTED_STATE,
                        attempt,
                        grace_wait_count,
                        observed,
                        "unexpected_state_after_recovery",
                    )
                if retryable_from is not None and attempt < policy.max_attempts:
                    # Cleanup changed the UI. A productive retry needs new
                    # evidence after recovery, not its last pre-failure frame.
                    fresh = observe()
                    if fresh.sequence <= observed.sequence:
                        return finish(
                            name, VerifiedTransitionOutcome.TIMEOUT, attempt,
                            grace_wait_count, fresh, "retry_state_not_fresh",
                        )
                    observed = fresh
                    if abort_if is not None and abort_if(observed):
                        return finish(
                            name, VerifiedTransitionOutcome.UNEXPECTED_STATE,
                            attempt, grace_wait_count, observed,
                            "unexpected_state_after_recovery",
                        )
                    if expected(observed):
                        return finish_late_success(
                            VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
                            attempt, grace_wait_count, observed,
                        )
            if _state.effect_accredited:
                return finish(
                    name, VerifiedTransitionOutcome.TIMEOUT, attempt,
                    grace_wait_count, observed, "effect_accredited_not_ready",
                )
            if retryable_from is None:
                return finish(
                    name,
                    VerifiedTransitionOutcome.TIMEOUT,
                    attempt,
                    grace_wait_count,
                    observed,
                    "expected_state_not_reached",
                )
            if not retryable_from(observed):
                if policy.retry_guard_timeout == 0:
                    return finish(
                        name,
                        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
                        attempt,
                        grace_wait_count,
                        observed,
                        "retry_guard_rejected",
                    )
                guarded = wait(
                    lambda snapshot: (
                        expected(snapshot) or retryable_from(snapshot)
                    ),
                    after_sequence=observed.sequence,
                    timeout=policy.retry_guard_timeout,
                    abort_if=abort_if,
                    stable_for=0.0,
                )
                if isinstance(guarded, RuntimeSnapshot):
                    observed = guarded
                    if expected(observed):
                        outcome = (
                            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                            if attempt == 1
                            else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                        )
                        return finish_late_success(outcome, attempt, grace_wait_count, observed)
                elif isinstance(guarded, RuntimeWaitAborted):
                    return finish(
                        name,
                        VerifiedTransitionOutcome.UNEXPECTED_STATE,
                        attempt,
                        grace_wait_count,
                        guarded.snapshot,
                        str(guarded),
                    )
                else:
                    return finish(
                        name,
                        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
                        attempt,
                        grace_wait_count,
                        guarded.last_snapshot or observed,
                        "retry_guard_rejected",
                    )
            if attempt >= policy.max_attempts:
                return finish(
                    name,
                    VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED,
                    attempt,
                    grace_wait_count,
                    observed,
                    "attempts_exhausted",
                )
            self._record(
                "transition.retry",
                transition=name,
                attempt=attempt + 1,
            )
            current = observed

        raise AssertionError("bounded transition loop exited unexpectedly")

    def _wait(
        self,
        expected: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None,
        stable_for: float,
        evidence: RuntimeEvidenceRequirements | None = None,
    ) -> RuntimeSnapshot | RuntimeWaitTimeout | RuntimeWaitAborted:
        check_operation()
        control = current_control()
        options = {}
        # RuntimeObserver inherits the operation's cancellation context. Keep
        # old wait adapters callable without adding an unsolicited keyword.
        if evidence is not None:
            options["evidence"] = evidence
        try:
            with operation_phase("observation"):
                if control is not None:
                    timeout = min(timeout, control.remaining())
                    if timeout <= 0:
                        raise OperationBudgetExpired("operation budget exhausted")
                snapshot = self.observer.wait_until(
                    expected, after_sequence=after_sequence, timeout=timeout,
                    abort_if=abort_if, stable_for=stable_for, **options,
                )
                check_operation()
                return snapshot
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            check_operation()
            return error

    def _try_recover(
        self,
        snapshot: RuntimeSnapshot,
        condition: Callable[[RuntimeSnapshot], bool],
        name: str,
        on_recovery: Callable[[], None] | None = None,
        *,
        regions: EvidenceRegions = (),
        target=None,
        evidence: RuntimeEvidenceRequirements | None = None,
    ) -> RuntimeSnapshot | None:
        check_operation()
        recovery = self.obstruction_recovery
        if recovery is None:
            return None
        if callable(regions):
            regions = regions(snapshot)
        try:
            with operation_phase("recovery"):
                check_operation()
                options = {"evidence": evidence} if evidence is not None else {}
                if regions or target is not None:
                    recovered = recovery.attempt(snapshot, condition, regions=regions, target=target, **options)
                else:
                    recovered = recovery.attempt(snapshot, condition, **options)
                check_operation()
        except RuntimeWaitCancelled:
            raise
        except Exception as error:
            self._record(
                "transition.obstruction_recovery_failed",
                transition=name,
                error=f"{type(error).__name__}: {error}",
            )
            raise
        if recovered is not None and not isinstance(
            recovered, RuntimeSnapshot
        ):
            self._record(
                "transition.obstruction_recovery_failed",
                transition=name,
                error="recovery_must_return_snapshot_or_none",
            )
            raise TypeError("recovery_must_return_snapshot_or_none")
        if recovered is not None and recovered.sequence <= snapshot.sequence:
            raise RuntimeWaitTimeout(
                after_sequence=snapshot.sequence,
                timeout=0.0,
                last_snapshot=recovered,
            )
        if recovered is not None and on_recovery is not None:
            on_recovery()
        check_operation()
        return recovered

    def _result(
        self,
        name: str,
        outcome: VerifiedTransitionOutcome,
        attempt_count: int,
        grace_wait_count: int,
        final_snapshot: RuntimeSnapshot,
        error: str | None = None,
        *,
        failure: FailureCause | None = None,
        action_source_snapshot: RuntimeSnapshot | None = None,
        recovery_after_action: bool = False,
    ) -> VerifiedTransitionResult:
        result = VerifiedTransitionResult(
            name=name,
            outcome=outcome,
            attempt_count=attempt_count,
            grace_wait_count=grace_wait_count,
            final_snapshot=final_snapshot,
            action_source_snapshot=action_source_snapshot,
            recovery_after_action=recovery_after_action,
            error=error,
            failure=failure or (
                FailureCause.from_error(error, kind=outcome.value, step=name, sequence=final_snapshot.sequence)
                if error is not None else None
            ),
        )
        return result

    def _record(self, event: str, **fields: object) -> None:
        if self.events is None:
            return
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _non_negative_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = (
    "ObstructionRecovery",
    "VerifiedTransition",
    "VerifiedTransitionOutcome",
    "VerifiedTransitionPolicy",
    "VerifiedTransitionResult",
)
