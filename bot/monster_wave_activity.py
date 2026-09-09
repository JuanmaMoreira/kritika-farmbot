"""One fresh, verified MAX SKIP attempt, Battle Mode hub -> hub."""
from dataclasses import dataclass
from enum import Enum

from bot.battle_mode_zone import is_battle_mode_select
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
)
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_semantics import *
from bot.runtime_observer import RuntimeWaitCancelled
from bot.runtime_facts import FactReadStatus
from bot.ocr_extractors import RESOURCE_SAPPHIRES
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


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


def boundary(snapshot):
    return (mw_screen(snapshot) and len(snapshot.state.overlays) == 1
            and set(snapshot.state.overlays) <= {
                POPUP_MW_INSUFFICIENT, POPUP_MW_BOARD, POPUP_MW_CLEAR, *HARD_BLOCKERS})


@dataclass(frozen=True)
class MonsterWaveResult(FlowResult):
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


class _Stopped(Exception):
    def __init__(self, result):
        self.result = result


class MonsterWaveActivity:
    name = 'monster_wave'
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
                            (ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),))

    def __init__(self, observer, actions, events, *, config=MonsterWaveConfig(),
                 cancel_requested=lambda: False, verified_transition=None, facts=None):
        if not isinstance(config, MonsterWaveConfig):
            raise ValueError('config must be MonsterWaveConfig')
        self.observer, self.actions, self.events = observer, actions, events
        self.config, self.cancel_requested = config, cancel_requested
        self.facts = facts
        self.verified_transition = verified_transition or VerifiedTransition(observer, actions, events)

    def run(self, *, daily_sapphires=False):
        transitions, events = [], []

        def finish(status=FlowStatus.COMPLETED, **kwargs):
            return MonsterWaveResult(status, events=tuple(events), **kwargs,
                transition_outcomes=tuple((r.name, r.outcome.value) for r in transitions),
                transition_attempts=tuple((r.name, r.attempt_count, r.grace_wait_count) for r in transitions))

        def check_cancel():
            if self.cancel_requested():
                raise RuntimeWaitCancelled()

        def step(name, intent, before, guard, expected):
            check_cancel()
            r = self.verified_transition.execute(
                f'monster_wave.{name}', intent, before, precondition=guard,
                expected=expected, policy=VerifiedTransitionPolicy(max_attempts=1), stable_for=.25)
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
            step('exit', ExitMonsterWave(), before, clean_mw, is_battle_mode_select)
            return finish()

        try:
            check_cancel()
            initial = self.observer.observe()
            before = self.observer.wait_until(
                is_battle_mode_select, after_sequence=initial.sequence,
                timeout=6, stable_for=.25, cancel_requested=self.cancel_requested)
            entered = step('open', OpenMonsterWave(), before, is_battle_mode_select,
                           entry_ready)
            current = entered
            for _ in range(2):
                obstruction = next((name for name in ENTRY_ACKNOWLEDGEMENTS
                                    if popup(name)(current)), None)
                if obstruction is None:
                    break
                current = step('acknowledge_entry', ENTRY_ACKNOWLEDGEMENTS[obstruction](),
                               current, popup(obstruction),
                               lambda s: entry_ready(s) and not popup(obstruction)(s))
            if skip_state(current) is None:
                raise ValueError('entry normalization did not reach clean MW within two acknowledgements')
            if daily_sapphires:
                # Only Daily composition enables this guard. Never use Lobby's old fact.
                read = self.facts.read_sapphires(
                    context=SCREEN_MONSTER_WAVE, after_sequence=current.sequence,
                    timeout=6, cancel_requested=self.cancel_requested)
                check_cancel()
                if read.status is FactReadStatus.CANCELLED:
                    raise RuntimeWaitCancelled()
                fact = read.fact
                if (read.status is not FactReadStatus.CONFIRMED or fact is None
                        or fact.name != RESOURCE_SAPPHIRES or fact.context != SCREEN_MONSTER_WAVE
                        or not fact.evidence
                        or any(e.sequence <= current.sequence for e in fact.evidence)):
                    raise ValueError(f'fresh MW sapphires not confirmed: {read.status.value}')
                current = self.observer.wait_until(
                    lambda s: skip_state(s) is not None,
                    after_sequence=max(e.sequence for e in (*read.evidence, *fact.evidence)),
                    timeout=6, stable_for=.25, cancel_requested=self.cancel_requested)
                if fact.value < 4:
                    business('daily_sapphires_below_minimum', observed_balance=fact.value,
                             required_sapphires=4, attempt_started=False,
                             observation_sequence=max(e.sequence for e in fact.evidence))
                    return exit_hub(current)
            # All decisions are local to this run and evidence; no activation cache.
            if skip_state(current) is SkipState.NEEDS_TICKETS:
                if not self.config.purchase_skip_tickets:
                    business('tickets_missing_purchase_disabled')
                    return exit_hub(current)
                current = step('open_tickets', OpenMonsterWaveTickets(), current,
                               lambda s: skip_state(s) is SkipState.NEEDS_TICKETS, popup(POPUP_MW_PURCHASE))
                full = lambda s: popup(POPUP_MW_PURCHASE)(s) and has(s, MW_PURCHASE_FULL)
                if not full(current):
                    # Fill All buys the game's remaining quantity. Never repeat a spend.
                    current = step('fill_tickets', FillMonsterWaveTickets(), current,
                                   lambda s: popup(POPUP_MW_PURCHASE)(s) and not has(s, MW_PURCHASE_FULL), full)
                    business('tickets_purchased')
                current = step('close_tickets', CloseMonsterWaveTickets(), current, full,
                               lambda s: skip_state(s) is SkipState.READY)
            if skip_state(current) is SkipState.READY:
                current = step('activate', ActivateMonsterWaveSkip(), current,
                               lambda s: skip_state(s) is SkipState.READY, active)
            current = step('select_max', SelectMonsterWaveMax(), current, active, max_ready)
            current = step('start_skip', StartMonsterWaveSkip(), current, max_ready, boundary)
            if popup(POPUP_MW_INSUFFICIENT)(current):
                business('insufficient_sapphires')
                current = step('reject_sapphires', RejectMonsterWaveSapphires(), current,
                               popup(POPUP_MW_INSUFFICIENT), clean_mw)
                return exit_hub(current)
            if popup(POPUP_MW_BOARD)(current):
                if not self.config.continue_when_nonblocking_inventory_full:
                    business('inventory_warning_declined')
                    current = step('decline_inventory', DeclineMonsterWaveInventory(), current,
                                   popup(POPUP_MW_BOARD), clean_mw)
                    return exit_hub(current)
                current = step('accept_inventory', AcceptMonsterWaveInventory(), current,
                               popup(POPUP_MW_BOARD),
                               lambda s: boundary(s) and POPUP_MW_BOARD not in s.state.overlays)
            blockers = set(current.state.overlays) & HARD_BLOCKERS
            if blockers:
                business('manual_resolution', blocker=next(iter(blockers)), reason='relief_return_not_acquired')
                return finish(FlowStatus.MANUAL_RESOLUTION)
            if not popup(POPUP_MW_CLEAR)(current):
                raise ValueError('unexpected_skip_boundary')
            business('completed')
            current = step('acknowledge_clear', AcknowledgeMonsterWaveClear(), current,
                           popup(POPUP_MW_CLEAR), clean_mw)
            return exit_hub(current)
        except RuntimeWaitCancelled:
            return finish(FlowStatus.CANCELLED)
        except _Stopped as error:
            r = error.result
            return finish(FlowStatus.FAILED, error=f'{r.name}: {r.outcome.value}: {r.error}', failure=r.failure)
        except Exception as error:
            return finish(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                          failure=FailureCause.from_error(error, kind='exception'))
