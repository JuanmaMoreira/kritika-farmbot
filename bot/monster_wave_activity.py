"""Verified MW preparation and reusable SKIP pass."""
from dataclasses import dataclass, replace
from enum import Enum
import time

from bot.battle_mode_zone import is_battle_mode_select, is_lobby
from bot.catalog import (POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL,
                         SCREEN_BATTLE_MODE_SELECT, SEMANTIC_CONFIDENCE_THRESHOLD)
from bot.component_contracts import ComponentRequirement
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowContract, FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.monster_wave_actions import (
    OpenMonsterWave, ExitMonsterWave, OpenMonsterWaveTickets, FillMonsterWaveTickets,
    CloseMonsterWaveTickets, ActivateMonsterWaveSkip, SelectMonsterWaveMax,
    StartMonsterWaveSkip, RejectMonsterWaveSapphires, DeclineMonsterWaveInventory,
    AcceptMonsterWaveInventory, AcknowledgeMonsterWaveClear,
    AcknowledgeMonsterWaveWeekly, AcknowledgeMonsterWaveRanking,
    AcknowledgeMonsterWavePointsReward,
)
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_semantics import *
from bot.runtime_observer import RuntimeWaitCancelled
from bot.runtime_facts import FactReadStatus
from bot.ocr_extractors import RESOURCE_SAPPHIRES
from bot.sapphire_pressure import sapphire_pressure_passes
from bot.perception.monster_wave import MONSTER_WAVE_SPECS
from bot.semantic_actions import OpenBattleModeSelect
from bot.state import ResolutionStatus
from bot.verified_transition import (VerifiedTransition, VerifiedTransitionPolicy,
                                     VerifiedTransitionOutcome)


class SkipState(str, Enum):
    NEEDS_TICKETS = 'needs_tickets'
    READY = 'ready'
    ACTIVE = 'active'


def has(snapshot, *names):
    present = {o.name for o in snapshot.observations.observations
               if o.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD}
    return set(names) <= present


def mw_screen(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_MONSTER_WAVE)


def clean_mw(snapshot):
    return mw_screen(snapshot) and not snapshot.state.overlays


def skip_state(snapshot):
    """Resolve only coherent, unobstructed evidence from this frame."""
    if not clean_mw(snapshot):
        return None
    needs = has(snapshot, MW_NEEDS_TICKETS)
    ready = has(snapshot, MW_READY)
    timer = has(snapshot, MW_TIMER)
    start = has(snapshot, MW_SKIP_START)
    if needs and not (ready or timer or start):
        return SkipState.NEEDS_TICKETS
    if ready and not (needs or timer or start):
        return SkipState.READY
    if timer and start and not (needs or ready):
        return SkipState.ACTIVE
    return None


def active(snapshot):
    return skip_state(snapshot) is SkipState.ACTIVE


def max_ready(snapshot):
    # Positive unobstructed controls are mandatory: absent tooltip alone is unsafe.
    return active(snapshot) and has(snapshot, MW_MAX, MW_CONTROLS_CLEAR) and not has(snapshot, MW_TOOLTIP)


def popup(name):
    return lambda s: mw_screen(s) and set(s.state.overlays) == {name}


HARD_BLOCKERS = {POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL}
ENTRY_ACKNOWLEDGEMENTS = {
    POPUP_MW_WEEKLY: AcknowledgeMonsterWaveWeekly,
    POPUP_MW_RANKING: AcknowledgeMonsterWaveRanking,
}


def entry_ready(snapshot):
    return (skip_state(snapshot) is not None
            or any(popup(name)(snapshot) for name in ENTRY_ACKNOWLEDGEMENTS))


def _entry_modal(snapshot):
    """Recognition only; UNKNOWN needs the local effective-entry handoff to ACK."""
    for name, landmark in ((POPUP_MW_WEEKLY, MW_WEEKLY), (POPUP_MW_RANKING, MW_RANKING)):
        if popup(name)(snapshot):
            return name
        if (snapshot.state.status is ResolutionStatus.UNKNOWN
                and set(snapshot.state.overlays) == {name} and has(snapshot, landmark)):
            return name
    return None


def boundary(snapshot):
    return (mw_screen(snapshot) and len(snapshot.state.overlays) == 1
            and set(snapshot.state.overlays) <= {
                POPUP_MW_INSUFFICIENT, POPUP_MW_BOARD, POPUP_MW_CLEAR,
                POPUP_MW_POINTS_REWARD, *HARD_BLOCKERS})


@dataclass(frozen=True)
class MonsterWaveResult(FlowResult):
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()
    board_sequence: int | None = None
    sapphires_initial: int | None = None
    sapphires_consumed: int = 0

    def __post_init__(self):
        super().__post_init__()
        if self.status is FlowStatus.RESOURCE_BOARD_PENDING:
            if type(self.board_sequence) is not int or self.board_sequence < 1:
                raise ValueError('pending resource board requires its fresh sequence')
        elif self.board_sequence is not None:
            raise ValueError('only a pending resource board can carry board_sequence')
        if self.sapphires_consumed < 0:
            raise ValueError('sapphires_consumed must be non-negative')


class _Stopped(Exception):
    def __init__(self, result):
        self.result = result


class MonsterWaveActivity:
    name = 'monster_wave'
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
                            (ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),))

    def __init__(self, observer, actions, events, *, config=MonsterWaveConfig(),
                 cancel_requested=lambda: False, verified_transition=None, facts=None,
                 clock=time.monotonic, sleeper=time.sleep):
        if not isinstance(config, MonsterWaveConfig):
            raise ValueError('config must be MonsterWaveConfig')
        self.observer, self.actions, self.events = observer, actions, events
        self.config, self.cancel_requested = config, cancel_requested
        self.facts = facts
        self.clock, self.sleeper = clock, sleeper
        self.verified_transition = verified_transition or VerifiedTransition(observer, actions, events)

    def prepare(self, *, pressure_relief=False):
        return self._run_phase('prepare', pressure_relief=pressure_relief)

    def read_sapphires_after_clear(self):
        """Read the existing MW HUD after the verified CLEAR dismissal."""
        if self.cancel_requested():
            raise RuntimeWaitCancelled()
        before = self.observer.observe()
        if not clean_mw(before):
            raise ValueError('mw_effect_requires_clean_context')
        read = self.facts.read_sapphires(
            context=SCREEN_MONSTER_WAVE, after_sequence=before.sequence,
            timeout=6, cancel_requested=self.cancel_requested)
        if self.cancel_requested() or read.status is FactReadStatus.CANCELLED:
            raise RuntimeWaitCancelled()
        fact = read.fact
        if (read.status is not FactReadStatus.CONFIRMED or fact is None
                or fact.name != RESOURCE_SAPPHIRES or fact.context != SCREEN_MONSTER_WAVE
                or type(fact.value) is not int or fact.value < 0 or not fact.evidence
                or any(e.sequence <= before.sequence for e in fact.evidence)
                or not 0 <= self.clock() - fact.timestamp <= 2.):
            raise ValueError('mw_fresh_sapphire_effect_unavailable')
        return fact

    def reenter(self):
        return self._run_phase('reenter')

    def run_pass(self, *, yield_resource_board=False, resume_after_relief=False):
        return self._run_phase('pass', yield_resource_board=yield_resource_board,
                               resume_after_relief=resume_after_relief)

    def finish_pass(self, current):
        return self._run_phase('finish', current=current)

    def leave(self, *, return_to_lobby=False):
        return self._run_phase('leave', return_to_lobby=return_to_lobby)

    def run(self, *, yield_resource_board=False, return_to_lobby=False, keep_current=False):
        """Single-pass compatibility for the bare MW flow."""
        prepared = self.prepare()
        if not prepared.succeeded or prepared.event_count('monster_wave.no_work'):
            return prepared
        passed = self.run_pass(yield_resource_board=yield_resource_board)
        combined = self._merge(prepared, passed)
        if not passed.succeeded:
            return combined
        if keep_current:
            if self.cancel_requested():
                return replace(combined, status=FlowStatus.CANCELLED)
            final = self.observer.observe()
            if not clean_mw(final):
                return replace(combined, status=FlowStatus.FAILED, error='mw_completion_surface_unconfirmed')
            return replace(combined, final_snapshot=final)
        return self._merge(combined, self.leave(return_to_lobby=return_to_lobby))

    @staticmethod
    def _merge(first, second):
        from dataclasses import replace
        return replace(second,
            events=first.events + second.events,
            transition_outcomes=first.transition_outcomes + second.transition_outcomes,
            transition_attempts=first.transition_attempts + second.transition_attempts,
            sapphires_initial=first.sapphires_initial,
            sapphires_consumed=first.sapphires_consumed + second.sapphires_consumed)

    def _run_phase(self, phase, *, yield_resource_board=False,
                   resume_after_relief=False, current=None, return_to_lobby=False,
                   pressure_relief=False):
        if type(return_to_lobby) is not bool:raise ValueError('return_to_lobby must be bool')
        if not isinstance(yield_resource_board, bool):
            raise ValueError('yield_resource_board must be bool')
        transitions, events = [], []

        def finish(status=FlowStatus.COMPLETED, **kwargs):
            return MonsterWaveResult(status, events=tuple(events), **kwargs,
                transition_outcomes=tuple((r.name, r.outcome.value) for r in transitions),
                transition_attempts=tuple((r.name, r.attempt_count, r.grace_wait_count) for r in transitions))

        def check_cancel():
            if self.cancel_requested():
                raise RuntimeWaitCancelled()

        def step(name, intent, before, guard, expected, *, abort_if=None):
            check_cancel()
            r = self.verified_transition.execute(
                f'monster_wave.{name}', intent, before, precondition=guard,
                expected=expected, policy=VerifiedTransitionPolicy(max_attempts=1),
                stable_for=.25, abort_if=abort_if)
            transitions.append(r)
            check_cancel()
            if not r.succeeded:
                raise _Stopped(r)
            if r.final_snapshot.sequence <= before.sequence or not expected(r.final_snapshot):
                raise ValueError(f'{name}: fresh postcondition not verified')
            return r.final_snapshot

        def business(kind, **fields):
            events.append(FlowEvent(f'monster_wave.{kind}', fields=fields))

        def exit_hub(before):
            returned = step('exit', ExitMonsterWave(), before, clean_mw,
                            lambda s: is_battle_mode_select(s) or is_lobby(s))
            # Prepared activities preserve their shared-hub postcondition. A
            # standalone caller owns Lobby completion: do not reopen that hub
            # when this fresh exit already reached its destination.
            from bot.event_log import record_best_effort
            record_best_effort(self.events,'monster_wave.exit.destination',
                physical='lobby' if is_lobby(returned) else 'battle_mode_select',
                requested='lobby' if return_to_lobby else 'battle_mode_select',
                source_sequence=returned.sequence)
            if is_lobby(returned) and not return_to_lobby:
                step('exit_lobby_to_hub', OpenBattleModeSelect(), returned,
                     is_lobby, is_battle_mode_select)
            return finish()

        def enter(before):
            def incompatible(s):
                return (s.state.status is ResolutionStatus.AMBIGUOUS
                        or (s.state.status is ResolutionStatus.RESOLVED and not mw_screen(s))
                        or not set(s.state.overlays) <= ENTRY_ACKNOWLEDGEMENTS.keys())

            # Recognition can end the passive wait without inventing a BASE.
            check_cancel()
            entered = self.verified_transition.execute(
                'monster_wave.open', OpenMonsterWave(), before,
                precondition=is_battle_mode_select,
                expected=lambda s: entry_ready(s) or _entry_modal(s) is not None,
                abort_if=lambda s: not is_battle_mode_select(s) and incompatible(s),
                policy=VerifiedTransitionPolicy(max_attempts=1), stable_for=.25)
            transitions.append(entered)
            check_cancel()
            source = entered.action_source_snapshot
            if (source is None or not is_battle_mode_select(source)
                    or entered.recovery_after_action
                    or (not entered.succeeded and entered.outcome is not VerifiedTransitionOutcome.TIMEOUT)):
                raise _Stopped(entered)
            current = entered.final_snapshot
            if current.sequence <= source.sequence:
                raise ValueError('entry snapshot is not fresh')
            acknowledgements = 0
            recovered = False
            while True:
                check_cancel()
                modal = _entry_modal(current)
                if modal is not None:
                    if acknowledgements == 2:
                        raise ValueError('entry normalization exceeded two acknowledgements')
                    # Only this established control inherits effective entry.
                    # Every other popup()/UNKNOWN guard remains unchanged.
                    guard = lambda s: s.sequence > source.sequence and _entry_modal(s) == modal
                    changed = lambda s: (modal not in s.state.overlays
                        and (entry_ready(s) or _entry_modal(s) is not None
                             or (s.state.status is ResolutionStatus.UNKNOWN and not s.state.overlays)))
                    current = step('acknowledge_entry', ENTRY_ACKNOWLEDGEMENTS[modal](),
                                   current, guard, changed, abort_if=incompatible)
                    acknowledgements += 1
                    continue
                if skip_state(current) is not None:
                    return current
                # Only the missing BASE landmark is a causal signal here.
                # Unknown/foreign overlays and contradictory bases never probe.
                recovery = self.verified_transition.obstruction_recovery
                if (not recovered and recovery is not None
                        and current.state.status is ResolutionStatus.UNKNOWN
                        and not current.state.overlays and not has(current, MW_SCREEN)):
                    regions = tuple(spec.region for spec in MONSTER_WAVE_SPECS if spec.name == MW_SCREEN)
                    fresh = recovery.attempt(current, entry_ready, regions=regions,
                                             monster_wave_entry_source=source)
                    recovered = True
                    check_cancel()
                    if fresh is not None:
                        if fresh.sequence <= current.sequence:
                            raise ValueError('entry recovery snapshot is not fresh')
                        # Post-dismiss frame can be transitional (e.g., NEEDS
                        # placeholder before timer loads). Recovery success alone
                        # never decides entry; require stable revalidation so a
                        # transient first-ABSENT frame cannot trigger an
                        # immediate NEEDS exit before MAX/first SKIP.
                        current = self.observer.wait_until(
                            lambda s: entry_ready(s) or _entry_modal(s) is not None,
                            after_sequence=fresh.sequence,
                            timeout=6, stable_for=.25,
                            abort_if=incompatible,
                            cancel_requested=self.cancel_requested)
                        if current.sequence <= fresh.sequence:
                            raise ValueError('entry recovery snapshot is not fresh')
                        continue
                raise ValueError('entry normalization did not reach clean MW')

        try:
            check_cancel()
            if phase == 'prepare':
                initial = self.observer.observe()
                before = self.observer.wait_until(
                    is_battle_mode_select, after_sequence=initial.sequence,
                    timeout=6, stable_for=.25, cancel_requested=self.cancel_requested)
                read = self.facts.read_sapphires(
                    context=SCREEN_BATTLE_MODE_SELECT, after_sequence=before.sequence,
                    timeout=6, cancel_requested=self.cancel_requested)
                check_cancel()
                if read.status is FactReadStatus.CANCELLED:
                    raise RuntimeWaitCancelled()
                fact = read.fact
                if (read.status is not FactReadStatus.CONFIRMED or fact is None
                        or fact.name != RESOURCE_SAPPHIRES or fact.context != SCREEN_BATTLE_MODE_SELECT
                        or not fact.evidence or type(fact.value) is not int or fact.value < 0
                        or any(e.sequence <= before.sequence for e in fact.evidence)):
                    raise ValueError(f'fresh hub sapphires not confirmed: {read.status.value}')
                if (sapphire_pressure_passes(fact.value) == 0 if pressure_relief else fact.value == 0):
                    business('no_work', sapphires=fact.value)
                    return finish(sapphires_initial=fact.value)
                before = self.observer.wait_until(
                    is_battle_mode_select,
                    after_sequence=max(e.sequence for e in (*read.evidence, *fact.evidence)),
                    timeout=6, stable_for=.25, cancel_requested=self.cancel_requested)
                current = enter(before)
                # USER_GT: with sapphires to spend, missing tickets never ends
                # the flow. NEEDS always attempts Fill All once (Gold), then
                # READY must verify before Activate; ACTIVE skips both.
                # purchase_skip_tickets no longer gates productive preparation.
                if skip_state(current) is SkipState.NEEDS_TICKETS:
                    current = step('open_tickets', OpenMonsterWaveTickets(), current,
                                   lambda s: skip_state(s) is SkipState.NEEDS_TICKETS, popup(POPUP_MW_PURCHASE))
                    full = lambda s: popup(POPUP_MW_PURCHASE)(s) and has(s, MW_PURCHASE_FULL)
                    if not full(current):
                        current = step('fill_tickets', FillMonsterWaveTickets(), current,
                                       lambda s: popup(POPUP_MW_PURCHASE)(s) and not has(s, MW_PURCHASE_FULL), full)
                        business('tickets_purchased')
                    current = step('close_tickets', CloseMonsterWaveTickets(), current, full,
                                   lambda s: skip_state(s) is SkipState.READY)
                if skip_state(current) is SkipState.READY:
                    current = step('activate', ActivateMonsterWaveSkip(), current,
                                   lambda s: skip_state(s) is SkipState.READY, active)
                current = step('select_max', SelectMonsterWaveMax(), current, active, max_ready)
                return finish(sapphires_initial=fact.value)

            if phase == 'reenter':
                initial = self.observer.observe()
                before = self.observer.wait_until(
                    is_battle_mode_select, after_sequence=initial.sequence,
                    timeout=6, stable_for=.25, cancel_requested=self.cancel_requested)
                current = enter(before)
                if not max_ready(current):
                    raise ValueError('mw_reentry_requires_active_max')
                return finish()
            if phase == 'finish':
                if current is None:
                    raise ValueError('mw_finish_requires_board_result')
            else:
                current = self.observer.observe()
            if phase == 'leave':
                if not clean_mw(current):
                    raise ValueError('mw_leave_requires_clean_screen')
                return exit_hub(current)
            if phase not in {'pass', 'finish'} or (phase == 'pass' and not max_ready(current)):
                raise ValueError('mw_pass_requires_active_max')
            if phase == 'pass':
                current = step('start_skip', StartMonsterWaveSkip(), current, max_ready, boundary)
            if popup(POPUP_MW_INSUFFICIENT)(current):
                business('insufficient_sapphires')
                current = step('reject_sapphires', RejectMonsterWaveSapphires(), current,
                               popup(POPUP_MW_INSUFFICIENT), clean_mw)
                return finish()
            if popup(POPUP_MW_BOARD)(current):
                if yield_resource_board:
                    business('resource_board_pending', board_sequence=current.sequence)
                    return finish(FlowStatus.RESOURCE_BOARD_PENDING,
                                  board_sequence=current.sequence)
                if not (self.config.continue_when_nonblocking_inventory_full or resume_after_relief):
                    business('inventory_warning_declined')
                    current = step('decline_inventory', DeclineMonsterWaveInventory(), current,
                                   popup(POPUP_MW_BOARD), clean_mw)
                    return finish()
                current = step('accept_inventory', AcceptMonsterWaveInventory(), current,
                               popup(POPUP_MW_BOARD),
                               lambda s: not popup(POPUP_MW_BOARD)(s))
            blockers = {name for name in HARD_BLOCKERS if popup(name)(current)}
            if blockers:
                business('manual_resolution', blocker=next(iter(blockers)), reason='relief_return_not_acquired')
                return finish(FlowStatus.MANUAL_RESOLUTION)
            if not popup(POPUP_MW_CLEAR)(current):
                deadline = self.clock() + 60
                while not (popup(POPUP_MW_CLEAR)(current)
                           or popup(POPUP_MW_INSUFFICIENT)(current)
                           or any(popup(name)(current) for name in HARD_BLOCKERS)):
                    if popup(POPUP_MW_POINTS_REWARD)(current):
                        # The topmost MODAL owns interaction: ACK only its OK.
                        # step() returns a fresh postcondition-verified snapshot
                        # and the loop re-observes whatever the modal uncovered
                        # (normally CLEAR) instead of assuming it.
                        current = step('acknowledge_points_reward', AcknowledgeMonsterWavePointsReward(), current,
                                       popup(POPUP_MW_POINTS_REWARD), lambda s: not popup(POPUP_MW_POINTS_REWARD)(s))
                        continue
                    check_cancel()
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        raise ValueError('mw_skip_result_unobservable')
                    self.sleeper(min(1.0, remaining))
                    newer = self.observer.observe()
                    if newer.sequence <= current.sequence:
                        continue
                    current = newer
                if popup(POPUP_MW_INSUFFICIENT)(current):
                    business('insufficient_sapphires')
                    current = step('reject_sapphires', RejectMonsterWaveSapphires(), current,
                                   popup(POPUP_MW_INSUFFICIENT), clean_mw)
                    return finish()
                blockers = {name for name in HARD_BLOCKERS if popup(name)(current)}
                if blockers:
                    business('manual_resolution', blocker=next(iter(blockers)), reason='relief_return_not_acquired')
                    return finish(FlowStatus.MANUAL_RESOLUTION)
                if not popup(POPUP_MW_CLEAR)(current):
                    raise ValueError('unexpected_skip_boundary')
            business('completed')
            current = step('acknowledge_clear', AcknowledgeMonsterWaveClear(), current,
                           popup(POPUP_MW_CLEAR), clean_mw)
            return finish()
        except RuntimeWaitCancelled:
            return finish(FlowStatus.CANCELLED)
        except _Stopped as error:
            r = error.result
            return finish(FlowStatus.FAILED, error=f'{r.name}: {r.outcome.value}: {r.error}', failure=r.failure)
        except Exception as error:
            return finish(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                          failure=FailureCause.from_error(error, kind='exception'))
