"""MW Yes only: receipt-bound loading progress, never economic authority.

Both MW callers share this handoff to their existing passive result observer.
The original engine runs unchanged: no terminal, blocker or foreign-context
detector is removed. The auxiliary detector runs only after successful dispatch
and only when no credited boundary/contradiction already decides the frame.
"""
from dataclasses import replace

from bot.action_executor import ActionExecutor, DispatchState
from bot.event_context import event_context
from bot.event_log import record_best_effort
from bot.monster_wave_actions import AcceptMonsterWaveInventory
from bot.monster_wave_semantics import (SCREEN_MONSTER_WAVE, POPUP_MW_BOARD,
    POPUP_MW_CLEAR, POPUP_MW_INSUFFICIENT, POPUP_MW_POINTS_REWARD)
from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.operation_control import check_operation, current_control
from bot.perception.engine import PerceptionEngine
from bot.perception.global_loading import ACTIVITY_GLOBAL_LOADING, GlobalLoadingDetector
from bot.runtime_observer import RuntimeObserver, RuntimeEvidenceRequirements
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy

YES_CONTEXT_COVERAGE = 'monster_wave.yes_context'
BOUNDARIES = frozenset((POPUP_MW_CLEAR, POPUP_MW_INSUFFICIENT,
    POPUP_MW_POINTS_REWARD, POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL))


def _board(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_MONSTER_WAVE
        and snapshot.state.overlays == (POPUP_MW_BOARD,))


def _boundary(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_MONSTER_WAVE
        and len(snapshot.state.overlays) == 1
        and snapshot.state.overlays[0] in BOUNDARIES)


class _ContextCoverage:
    """Declare execution of the verified context vocabulary, without narrowing it."""
    def __init__(self, engine, window):
        self.engine, self.window = engine, window

    def analyze(self, frame):
        # RuntimeEvidenceRequirements may filter this frame before predicates;
        # still latch a witnessed source rotation so it cannot be forgotten.
        if frame.source_id != self.window.before.frame.source_id:
            self.window.valid = False
        batch = self.engine.analyze(frame)
        return replace(batch, coverage=(batch.coverage or frozenset()) | {YES_CONTEXT_COVERAGE})


class _ReceiptExecutor(ActionExecutor):
    """Delegate the exact input to its owner; retain its real returned receipt."""
    def __init__(self, delegate, window):
        self.delegate, self.window = delegate, window

    def execute(self, action, geometry, **kwargs):
        if not isinstance(action, AcceptMonsterWaveInventory):
            raise ValueError('MW Yes receipt adapter cannot dispatch other actions')
        result = self.delegate.execute(action, geometry, **kwargs)
        self.window.receipt = getattr(result, 'dispatch', None)
        self.window.operation_id = event_context()['operation_id']
        return result


class _YesProgress:
    def __init__(self, before, policy):
        self.before, self.policy = before, policy
        self.receipt = self.deadline = self.operation_id = self.snapshot = None
        self.valid = True
        self.detector = GlobalLoadingDetector()

    def contradictory(self, snapshot):
        bad = (snapshot.frame.source_id != self.before.frame.source_id
            or snapshot.state.status is ResolutionStatus.AMBIGUOUS
            or (snapshot.state.status is ResolutionStatus.RESOLVED
                and snapshot.state.base_context != SCREEN_MONSTER_WAVE)
            or (bool(snapshot.state.overlays) and (len(snapshot.state.overlays) != 1
                or snapshot.state.overlays[0] not in BOUNDARIES | {POPUP_MW_BOARD})))
        if bad:
            self.valid = False
        return bad

    def observed(self, snapshot):
        check_operation()
        # Terminal/blocker decisions precede this optional CV work, regardless
        # of whether loading coverage is available or the spinner persists.
        if _boundary(snapshot) or self.contradictory(snapshot) or not self.valid:
            return False
        receipt = self.receipt
        control = current_control()
        if (receipt is None or receipt.state is not DispatchState.ADB_RETURNED
            or receipt.completed_at is None or not receipt.operation_id
            or receipt.operation_id != self.operation_id
            or self.operation_id not in (event_context()['operation_id'], event_context()['parent_operation_id'])):
            return False
        if self.deadline is None:
            self.deadline = min(receipt.completed_at + self.policy.normal_timeout + self.policy.grace_timeout,
                                control.clock() + control.remaining())
        now = control.clock()
        if receipt.operation_id != self.operation_id or now >= self.deadline:
            self.valid = False
            return False
        evidence = RuntimeEvidenceRequirements(source_id=self.before.frame.source_id,
            captured_after=receipt.completed_at, max_age=2.,
            required_coverage=frozenset((YES_CONTEXT_COVERAGE,)))
        if snapshot.sequence <= self.before.sequence or not evidence.accepts(snapshot, now):
            return False
        emitted = self.detector.detect(snapshot.frame.image)
        check_operation()
        if control.clock() >= self.deadline or not evidence.accepts(snapshot, control.clock()):
            return False
        if not emitted:
            return False
        self.snapshot = replace(snapshot, observations=replace(snapshot.observations,
            observations=snapshot.observations.observations + tuple(emitted),
            coverage=snapshot.observations.coverage | {ACTIVITY_GLOBAL_LOADING}))
        return True


def execute_monster_wave_yes(transition, name, before, *, stable_for=0., cancel_requested=None):
    """One Yes; positive processing may hand off to the existing passive loop.

No useful signal preserves the prior board-disappearance handoff. This handoff
is readiness for result observation, not action effect. Only credited CLEAR is
passed to the phase1 effect field; loading is stored in progress_snapshot.
"""
    policy = VerifiedTransitionPolicy(max_attempts=1)
    observer = getattr(transition, 'observer', None)
    # Legacy/custom observers and executors retain their existing behavior.
    # No guessed coverage from missing observations or unsupported perception.
    if (not isinstance(transition, VerifiedTransition)
        or not isinstance(observer, RuntimeObserver)
        or type(observer.perception) is not PerceptionEngine
        or not isinstance(transition.actions, ActionExecutor)
        or not before.frame.source_id):
        return transition.execute(name, AcceptMonsterWaveInventory(), before,
            precondition=_board, expected=lambda s: not _board(s),
            policy=policy, stable_for=stable_for)
    from bot.perception import MONSTER_WAVE_ENTRY_READINESS_SCOPE, MONSTER_WAVE_BOARD_ACQUISITION_SCOPE
    from bot.perception.scope import ScopeSpec, select_detectors
    scope = ScopeSpec('monster_wave_yes_context',
        MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.spec_names,
        MONSTER_WAVE_ENTRY_READINESS_SCOPE.specialized_types)
    try:
        # Capability proof only; delegate the ENTIRE original engine below.
        select_detectors(observer.perception, scope)
    except ValueError:
        return transition.execute(name, AcceptMonsterWaveInventory(), before,
            precondition=_board, expected=lambda s: not _board(s),
            policy=policy, stable_for=stable_for)
    window = _YesProgress(before, policy)
    scoped = observer.scoped(_ContextCoverage(observer.perception, window))
    focal = VerifiedTransition(scoped, _ReceiptExecutor(transition.actions, window),
        transition.events, transition.obstruction_recovery,
        metrics_clock=transition._metrics_clock, clock=transition._clock,
        cancel_requested=cancel_requested or transition.cancel_requested)
    try:
        result = focal.execute(name, AcceptMonsterWaveInventory(), before,
            precondition=_board,
            # Phase 1 also checks expected before abort_if on reacquisition
            # after grace. Keep contradictions dominant on that path too.
            expected=lambda s: not window.contradictory(s) and (not _board(s)
                or (window.snapshot is not None and window.snapshot.sequence == s.sequence)),
            effect_observed=lambda s: _boundary(s) and s.state.overlays == (POPUP_MW_CLEAR,),
            progress_observed=window.observed, abort_if=window.contradictory,
            evidence=RuntimeEvidenceRequirements(source_id=before.frame.source_id, max_age=2.),
            policy=policy, stable_for=stable_for)
    finally:
        scoped.flush_analysis_metrics()
    if result.progress_snapshot is not None and window.snapshot is not None:
        result = replace(result, progress_snapshot=window.snapshot)
        record_best_effort(transition.events, 'monster_wave.yes_loading_progress',
            operation_id=result.operation_id, dispatch_id=window.receipt.dispatch_id,
            source_id=window.snapshot.frame.source_id, sequence=window.snapshot.sequence,
            ready=result.ready, effect_accredited=result.effect_accredited)
    return result
