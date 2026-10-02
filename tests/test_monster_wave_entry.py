"""Offline regression of physical MW entry layering through real action/recovery owners."""
from dataclasses import replace

import pytest

from bot.monster_wave_activity import popup
from bot.monster_wave_actions import (AcknowledgeMonsterWaveRanking,
    AcknowledgeMonsterWaveWeekly, OpenMonsterWave)
from bot.monster_wave_semantics import (
    MW_RANKING, MW_WEEKLY, POPUP_MW_RANKING, POPUP_MW_WEEKLY, SCREEN_MONSTER_WAVE)
from bot.observations import Observation, ObservationSource
from bot.obstruction_recovery import PortalObstructionRecovery, ObstructionRecoveryPolicy
from bot.portal_notification import PortalProbeOutcome
from bot.runtime_observer import RuntimeWaitAborted
from bot.semantic_actions import DismissPortalNotification
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition
from test_monster_wave import Device, ACTIVE, MAX, NEEDS
from test_portal_obstruction_recovery import FakeClock


class OccludedEntry(Device):
    def __init__(self, entry=POPUP_MW_RANKING, *, clear_on_ack=False,
                 unresolved=True, outcome=PortalProbeOutcome.CONFIRMED,
                 modal_after_dismiss=None, persistent=False, **kwargs):
        super().__init__(entry, **kwargs)
        self.hidden = unresolved
        self.portal_visible = True
        self.clear_on_ack = clear_on_ack
        self.outcome = outcome
        self.modal_after_dismiss = modal_after_dismiss
        self.persistent = persistent
        self.probes = []
        self.observed = []

    def observe(self):
        s = super().observe()
        if self.base == SCREEN_MONSTER_WAVE:
            names = {POPUP_MW_RANKING: MW_RANKING, POPUP_MW_WEEKLY: MW_WEEKLY}
            evidence = tuple(Observation(names[n], .996, ObservationSource.LOCAL_CV)
                             for n in self.overlays if n in names)
            s = replace(s, observations=replace(s.observations,
                observations=s.observations.observations + evidence))
            if self.hidden:
                s = replace(s, state=replace(s.state, status=ResolutionStatus.UNKNOWN,
                                             base_context=None))
        self.observed.append(s)
        return s

    def target_for(self, action):
        return self.executor.target_for(action)

    def wait_until(self, predicate, **kwargs):
        def checked(s):
            if kwargs.get('abort_if') is not None and kwargs['abort_if'](s):
                raise RuntimeWaitAborted(s)
            return predicate(s)
        return super().wait_until(checked, **kwargs)

    def execute(self, action, geometry):
        if isinstance(action, DismissPortalNotification):
            self.intents.append(type(action).__name__)
            self.trace.append(('intent', type(action).__name__))
            self.executor.execute(action, geometry)
            if not self.persistent:
                self.portal_visible = False
                self.hidden = False
                if self.modal_after_dismiss:
                    self.overlays = (self.modal_after_dismiss,)
            return
        super().execute(action, geometry)
        if self.clear_on_ack and isinstance(action, (AcknowledgeMonsterWaveRanking, AcknowledgeMonsterWaveWeekly)):
            self.hidden = False

    def probe(self, image):
        self.probes.append(self.sequence)
        self.trace.append(('probe', self.sequence))
        # Causal discovery is forbidden below either modal. Settlement after
        # dismiss may observe a newly exposed modal while verifying ABSENT.
        if 'DismissPortalNotification' not in self.intents:
            assert not self.overlays
        return self.outcome if self.portal_visible else PortalProbeOutcome.ABSENT

    def activity(self):
        activity = super().activity()
        clock = FakeClock()
        recovery = PortalObstructionRecovery(self, self, self,
            policy=ObstructionRecoveryPolicy(settle_timeout=1),
            clock=clock.clock, sleeper=clock.sleeper)
        activity.verified_transition = VerifiedTransition(self, self, self.events,
                                                         obstruction_recovery=recovery)
        return activity


@pytest.mark.parametrize('modal,ack', [(POPUP_MW_RANKING, 'AcknowledgeMonsterWaveRanking'),
                                      (POPUP_MW_WEEKLY, 'AcknowledgeMonsterWaveWeekly')])
@pytest.mark.parametrize('phase', ['prepare', 'reenter'])
def test_effective_entry_authorizes_only_fresh_modal_ack_under_unknown(modal, ack, phase):
    d = OccludedEntry(modal, clear_on_ack=True, entry_after=MAX)
    assert getattr(d.activity(), phase)().succeeded
    assert d.intents[:2] == ['OpenMonsterWave', ack]
    assert d.probes == []  # H&H stays visible but is irrelevant after the ACK.
    unknown = [s for s in d.observed if s.state.status is ResolutionStatus.UNKNOWN]
    assert unknown and all(not popup(modal)(s) for s in unknown)
    i = d.trace.index(('intent', ack))
    assert d.trace[i + 2][0] == 'observe'  # Intent, physical tap, fresh snapshot.


@pytest.mark.parametrize('first,second', [(POPUP_MW_RANKING, POPUP_MW_WEEKLY),
                                         (POPUP_MW_WEEKLY, POPUP_MW_RANKING)])
def test_both_modal_orders_precede_any_portal_probe(first, second):
    class TwoModals(OccludedEntry):
        def execute(self, action, geometry):
            if isinstance(action, (AcknowledgeMonsterWaveRanking, AcknowledgeMonsterWaveWeekly)):
                self.entry_after = second if not any('Acknowledge' in a for a in self.intents) else ACTIVE
            super().execute(action, geometry)

    d = TwoModals(first)
    assert d.activity().prepare().succeeded
    assert all('Acknowledge' in a for a in d.intents[1:3])
    assert d.intents[3:] == ['DismissPortalNotification', 'SelectMonsterWaveMax']
    assert len(d.probes) == 2  # One causal probe + fresh ABSENT confirmation.
    assert max(i for i, t in enumerate(d.trace) if t[0] == 'intent' and 'Acknowledge' in t[1]) < next(
        i for i, t in enumerate(d.trace) if t[0] == 'probe')


def test_live_ranking_regression_ack_then_causal_cleanup_then_entry_revalidation():
    d = OccludedEntry()
    result = d.activity().prepare()
    assert result.succeeded, result.error
    assert d.intents == ['OpenMonsterWave', 'AcknowledgeMonsterWaveRanking',
                         'DismissPortalNotification', 'SelectMonsterWaveMax']
    assert len(d.probes) == 2 and d.probes[1] > d.probes[0]
    pre_probe = next(s for s in d.observed if s.sequence == d.probes[0])
    assert pre_probe.state.status is ResolutionStatus.UNKNOWN and not pre_probe.state.overlays
    assert next(s for s in d.observed if s.sequence == d.probes[1]).state.base_context == SCREEN_MONSTER_WAVE


def test_dismiss_restarts_entry_analysis_and_can_expose_known_modal():
    d = OccludedEntry(ACTIVE, modal_after_dismiss=POPUP_MW_WEEKLY)
    assert d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave', 'DismissPortalNotification',
                         'AcknowledgeMonsterWaveWeekly', 'SelectMonsterWaveMax']


@pytest.mark.parametrize('outcome', [PortalProbeOutcome.ABSENT, PortalProbeOutcome.INCONCLUSIVE, None])
def test_unconfirmed_causal_probe_never_dismisses_or_continues(outcome):
    d = OccludedEntry(outcome=outcome)
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave', 'AcknowledgeMonsterWaveRanking']
    assert len(d.probes) == 1


def test_persistent_portal_fails_without_second_dismiss_or_entry_input():
    d = OccludedEntry(persistent=True)
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave', 'AcknowledgeMonsterWaveRanking', 'DismissPortalNotification']


def test_irrelevant_visible_portal_on_normal_entry_never_probes():
    d = OccludedEntry(ACTIVE, unresolved=False)
    assert d.activity().prepare().succeeded
    assert d.portal_visible and not d.probes
    assert d.intents == ['OpenMonsterWave', 'SelectMonsterWaveMax']


def test_unknown_popup_under_unknown_never_authorizes_any_followup_input():
    d = OccludedEntry('popup.unknown')
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave'] and not d.probes


def test_failed_executor_cannot_create_entry_handoff():
    class FailedEntry(OccludedEntry):
        def execute(self, action, geometry):
            super().execute(action, geometry)
            if isinstance(action, OpenMonsterWave):
                raise RuntimeError('partly executed entry')
    d = FailedEntry()
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave'] and not d.probes


def test_existing_unknown_without_entry_handoff_does_not_authorize_ack():
    d = OccludedEntry(base=SCREEN_MONSTER_WAVE)
    d.overlays = (POPUP_MW_RANKING,)
    assert not d.activity().prepare().succeeded
    assert not d.intents and not d.probes


def test_missing_entry_signal_outside_envelope_never_probes(monkeypatch):
    import bot.monster_wave_activity as owner
    monkeypatch.setattr(owner, 'MONSTER_WAVE_SPECS', tuple(
        replace(spec, region=(.6, .6, .8, .8)) for spec in owner.MONSTER_WAVE_SPECS))
    d = OccludedEntry()
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave', 'AcknowledgeMonsterWaveRanking']
    assert not d.probes


def test_persistent_entry_modal_never_probes_underneath_it():
    d = OccludedEntry(entry_after=POPUP_MW_RANKING)
    assert not d.activity().prepare().succeeded
    assert d.intents == ['OpenMonsterWave', 'AcknowledgeMonsterWaveRanking']
    assert not d.probes


def test_stale_entry_modal_cannot_authorize_ack():
    class StaleEntry(OccludedEntry):
        def activity(self):
            activity = super().activity()
            execute = activity.verified_transition.execute
            def stale(*args, **kwargs):
                from test_world_boss_flow import snapshot
                result = execute(*args, **kwargs)
                return replace(result, final_snapshot=snapshot(
                    result.action_source_snapshot.sequence,
                    overlays=(POPUP_MW_RANKING,),
                    semantic_observations=result.final_snapshot.observations.observations))
            activity.verified_transition.execute = stale
            return activity
    d = StaleEntry()
    result = d.activity().prepare()
    assert not result.succeeded and result.error == 'entry snapshot is not fresh'
    assert d.intents == ['OpenMonsterWave'] and not d.probes


@pytest.mark.parametrize('conflict', ['foreign', 'ambiguous', 'unknown_popup'])
def test_observed_contradiction_invalidates_entry_even_if_next_frame_has_known_modal(conflict):
    class TransientConflict(OccludedEntry):
        contradicted = False

        def observe(self):
            s = super().observe()
            if self.base != SCREEN_MONSTER_WAVE or self.contradicted:
                return s
            self.contradicted = True
            if conflict == 'foreign':
                state = replace(s.state, status=ResolutionStatus.RESOLVED, base_context='screen.guild')
            elif conflict == 'ambiguous':
                state = replace(s.state, status=ResolutionStatus.AMBIGUOUS,
                                base_candidates=('screen.guild', SCREEN_MONSTER_WAVE))
            else:
                state = replace(s.state, overlays=('popup.unknown',))
            return replace(s, state=state)

    d = TransientConflict()
    result = d.activity().prepare()
    assert not result.succeeded and 'unexpected_state' in result.error
    assert d.intents == ['OpenMonsterWave'] and not d.probes


def test_transient_needs_after_successful_hh_recovery_does_not_exit():
    """Live dfb99b37: Sapphires>0, H&H blocks, dismiss OK, first-ABSENT NEEDS
    placeholder must not trigger immediate Back; stable ACTIVE continues."""

    class TransientNeeds(OccludedEntry):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.served_transient = False

        def observe(self):
            s = super().observe()
            if ('DismissPortalNotification' in self.intents and not self.served_transient
                    and self.base == SCREEN_MONSTER_WAVE):
                self.served_transient = True
                transient = tuple(Observation(n, 1.0, ObservationSource.LOCAL_CV)
                                  for n in NEEDS)
                return replace(s, observations=replace(
                    s.observations, observations=transient))
            return s

    d = TransientNeeds(ACTIVE, entry_after=ACTIVE)
    result = d.activity().prepare()
    assert result.succeeded, result.error
    assert result.sapphires_initial == 100
    assert result.event_count('monster_wave.tickets_missing_purchase_disabled') == 0
    assert 'ExitMonsterWave' not in d.intents
    assert 'SelectMonsterWaveMax' in d.intents
    assert d.intents.index('DismissPortalNotification') < d.intents.index('SelectMonsterWaveMax')


def test_stable_needs_after_hh_recovery_still_exits_once_stable():
    """True 0/30 NEEDS proceeds through Fill All lifecycle (no terminal exit)."""
    d = OccludedEntry(NEEDS, entry_after=NEEDS)
    result = d.activity().prepare()
    assert result.succeeded
    assert result.event_count('monster_wave.tickets_missing_purchase_disabled') == 0
    assert result.event_count('monster_wave.tickets_purchased') == 1
    assert 'ExitMonsterWave' not in d.intents
    assert d.intents == ['OpenMonsterWave', 'DismissPortalNotification', 'OpenMonsterWaveTickets',
        'FillMonsterWaveTickets', 'CloseMonsterWaveTickets', 'ActivateMonsterWaveSkip',
        'SelectMonsterWaveMax']
