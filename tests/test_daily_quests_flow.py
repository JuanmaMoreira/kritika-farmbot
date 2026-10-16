from dataclasses import dataclass, replace
from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
)
from bot.daily_quests_flow import (
    DAILY_QUESTS_CLAIM_ALL_COMPLETED,
    DAILY_QUESTS_CLAIM_ALL_EXECUTED,
    DAILY_QUESTS_NOOP,
    DAILY_QUESTS_PROGRESS_REWARD_COMPLETED,
    DAILY_QUESTS_PROGRESS_REWARD_EXECUTED,
    DailyQuestsFlow,
)
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    ClaimAllDailyQuests,
    ClaimDailyQuestsProgressReward,
    CloseDailyQuests,
    OpenQuests,
    SelectDailyQuests,
)
from bot.state import ResolutionStatus, ResolvedState


@dataclass
class WaitCall:
    after_sequence: int
    stable_for: float


class ScriptedObserver:
    def __init__(self, initial, scripts, observe_sequence=None):
        self.initial = initial
        self.scripts = list(scripts)
        self.observe_sequence = list(observe_sequence) if observe_sequence else []
        self.observe_index = 0
        self.calls = []
        self._initial_returned = False

    def observe(self):
        if not self._initial_returned:
            self._initial_returned = True
            return self.initial
        if self.observe_index < len(self.observe_sequence):
            result = self.observe_sequence[self.observe_index]
            self.observe_index += 1
            return result
        return self.initial

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        cancel_requested=None,
        stable_for=0.0,
    ):
        self.calls.append(WaitCall(after_sequence, stable_for))
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for snapshot in script:
            last = snapshot
            assert snapshot.sequence > after_sequence
            if cancel_requested is not None and cancel_requested():
                raise RuntimeWaitCancelled("cancelled")
            if abort_if is not None and abort_if(snapshot):
                raise RuntimeWaitAborted(snapshot)
            if condition(snapshot):
                if stable_since is None:
                    stable_since = snapshot.timestamp
                if snapshot.timestamp - stable_since >= stable_for:
                    return snapshot
            else:
                stable_since = None
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence,
            timeout=timeout,
            last_snapshot=last,
        )


class Actions:
    def __init__(self):
        self.items = []

    def execute(self, action, geometry):
        self.items.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


def rows_observation():
    return Observation(
        "indicator.daily_quests_rows_populated",
        0.95,
        ObservationSource.LOCAL_CV,
    )


def snapshot(sequence, timestamp, *, base, overlays=(), status=None,
             observations=(), base_candidates=()):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, tuple(observations)),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(base_candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def run_flow(initial, scripts, *, observe_sequence=None, **kwargs):
    observer = ScriptedObserver(initial, scripts, observe_sequence=observe_sequence)
    actions = Actions()
    events = Events()
    kwargs.pop("observe_sequence", None)
    result = DailyQuestsFlow(observer, actions, events, **kwargs).run()
    return result, actions.items, events.items, observer


def stable_pair(first, second):
    return [first, second]


def test_daily_retry_rejects_repeated_and_regressing_frame_sequences():
    current = snapshot(10, 10.0, base=SCREEN_QUESTS)
    observer = ScriptedObserver(current, [], observe_sequence=[current] * 10)
    actions = Actions()
    now = [0.0]
    flow = DailyQuestsFlow(
        observer, actions, Events(), navigation_timeout=3,
        clock=lambda: now[0], sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    with pytest.raises(RuntimeWaitTimeout):
        flow._wait_for_daily_tab(current)
    assert actions.items == [SelectDailyQuests()]


def test_stale_daily_snapshot_cannot_authorize_claims_or_completion():
    current = snapshot(10, 10.0, base=SCREEN_QUESTS)
    stale_daily = snapshot(9, 9.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    observer = ScriptedObserver(stale_daily, [])
    now = [0.0]
    flow = DailyQuestsFlow(
        observer, Actions(), Events(), navigation_timeout=2,
        clock=lambda: now[0], sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    with pytest.raises(RuntimeWaitTimeout):
        flow._wait_for_daily_tab(current)


def test_noop_without_claims_never_touches_claim_all_or_karats():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    daily_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    daily_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    returned_a = snapshot(4, 3.0, base=SCREEN_LOBBY)
    returned_b = snapshot(5, 3.3, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(
        lobby,
        [stable_pair(daily_a, daily_b), stable_pair(returned_a, returned_b)],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert result.event_count(DAILY_QUESTS_NOOP) == 1
    assert actions == [OpenQuests(), CloseDailyQuests()]


def test_remembered_non_daily_tab_is_switched_to_daily_and_verified():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    quests_a = snapshot(2, 2.0, base=SCREEN_QUESTS)
    quests_b = snapshot(3, 2.3, base=SCREEN_QUESTS)
    daily_a = snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    daily_b = snapshot(5, 3.3, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    returned_a = snapshot(6, 4.0, base=SCREEN_LOBBY)
    returned_b = snapshot(7, 4.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(quests_a, quests_b),
            stable_pair(returned_a, returned_b),
        ],
        observe_sequence=[daily_a],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert actions == [OpenQuests(), SelectDailyQuests(), CloseDailyQuests()]
    assert [call.after_sequence for call in observer.calls] == [1, 4]


def test_daily_tab_selection_retries_once_when_still_non_daily_after_first_tap():
    """
    Regression: bounded retry when first tap doesn't activate Daily tab.

    non-Daily -> first SelectDailyQuests -> still non-Daily after ~1s ->
    second SelectDailyQuests -> Daily active -> proceed.

    Verifies SelectDailyQuests executes twice (generic retry contract).
    """
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    quests_a = snapshot(2, 2.0, base=SCREEN_QUESTS)
    quests_b = snapshot(3, 2.3, base=SCREEN_QUESTS)
    # After first tap: still non-Daily (retry condition)
    quests_c = snapshot(4, 3.3, base=SCREEN_QUESTS)
    quests_d = snapshot(5, 3.6, base=SCREEN_QUESTS)
    # After second tap: Daily becomes active
    daily_a = snapshot(6, 4.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    daily_b = snapshot(7, 4.3, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    returned_a = snapshot(8, 5.0, base=SCREEN_LOBBY)
    returned_b = snapshot(9, 5.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(quests_a, quests_b),
            stable_pair(returned_a, returned_b),
        ],
        observe_sequence=[quests_c, daily_a],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    # Two SelectDailyQuests taps (generic retry contract)
    assert actions == [
        OpenQuests(),
        SelectDailyQuests(),
        SelectDailyQuests(),
        CloseDailyQuests(),
    ]
    assert actions.count(SelectDailyQuests()) == 2
    # wait_until calls: OpenQuests (after 1), CloseDailyQuests (after 6)
    assert [call.after_sequence for call in observer.calls] == [1, 6]


def test_daily_tab_selection_is_single_attempt_and_fails_without_claim_or_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    quests_a = snapshot(2, 2.0, base=SCREEN_QUESTS)
    quests_b = snapshot(3, 2.3, base=SCREEN_QUESTS)
    result, actions, _, _ = run_flow(
        lobby,
        [
            stable_pair(quests_a, quests_b),
            RuntimeWaitTimeout(after_sequence=3, timeout=6.0, last_snapshot=None),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert actions == [OpenQuests(), SelectDailyQuests()]


def test_unknown_state_does_not_authorize_daily_tab_tap():
    """
    UNKNOWN/AMBIGUOUS state -> wait passively, no SelectDailyQuests tap on UNKNOWN frame.
    Taps only on clean Quests frames (before and after UNKNOWN).
    """
    from bot.state import ResolutionStatus
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    quests_a = snapshot(2, 2.0, base=SCREEN_QUESTS)
    quests_b = snapshot(3, 2.3, base=SCREEN_QUESTS)
    # UNKNOWN state (no base context)
    unknown = snapshot(4, 3.3, base=None, status=ResolutionStatus.UNKNOWN)
    # Then clean Quests again (recovery)
    quests_c = snapshot(5, 4.0, base=SCREEN_QUESTS)
    quests_d = snapshot(6, 4.3, base=SCREEN_QUESTS)
    # Then Daily becomes active
    daily_a = snapshot(7, 5.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    daily_b = snapshot(8, 5.3, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    returned_a = snapshot(9, 6.0, base=SCREEN_LOBBY)
    returned_b = snapshot(10, 6.3, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(
        lobby,
        [
            stable_pair(quests_a, quests_b),
            stable_pair(returned_a, returned_b),
        ],
        observe_sequence=[unknown, quests_c, daily_a],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    # Two taps: one on initial clean Quests (quests_b), one after UNKNOWN recovery (quests_c)
    # No tap on UNKNOWN frame itself
    assert actions == [
        OpenQuests(),
        SelectDailyQuests(),  # on initial quests_b
        SelectDailyQuests(),  # on recovered quests_c
        CloseDailyQuests(),
    ]
    assert actions.count(SelectDailyQuests()) == 2


def test_incompatible_resolved_context_aborts_daily_tab_selection():
    """
    Contradictory RESOLVED context (e.g. manage screen) -> aborts with RuntimeWaitAborted.
    """
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    quests_a = snapshot(2, 2.0, base=SCREEN_QUESTS)
    quests_b = snapshot(3, 2.3, base=SCREEN_QUESTS)
    # Incompatible: manage screen (base=screen.manage) while expecting Quests
    incompatible = snapshot(4, 3.3, base="screen.manage")

    result, actions, _, _ = run_flow(
        lobby,
        [
            stable_pair(quests_a, quests_b),
        ],
        observe_sequence=[incompatible],
    )

    assert result.status is FlowStatus.FAILED
    assert "state_wait_failed" in result.error
    # OpenQuests executed, then tap on clean Quests, then abort on incompatible
    assert actions == [OpenQuests(), SelectDailyQuests()]


def test_claim_disappearance_must_remain_stable_before_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    daily_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),))
    daily_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),))
    absent_once = snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    claim_reappears = snapshot(5, 3.2, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),))
    settled_a = snapshot(6, 3.4, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    settled_b = snapshot(7, 4.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    lobby_a = snapshot(8, 5.0, base=SCREEN_LOBBY)
    lobby_b = snapshot(9, 5.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(daily_a, daily_b),
            [absent_once, claim_reappears, settled_a, settled_b],
            stable_pair(lobby_a, lobby_b),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_executed and result.claim_all_completed
    assert result.event_count(DAILY_QUESTS_CLAIM_ALL_EXECUTED) == 1
    assert result.event_count(DAILY_QUESTS_CLAIM_ALL_COMPLETED) == 1
    assert actions == [OpenQuests(), ClaimAllDailyQuests(), CloseDailyQuests()]
    assert actions.count(ClaimAllDailyQuests()) == 1
    assert observer.calls[1].stable_for == pytest.approx(0.5)


def test_claim_all_reevaluates_and_claims_newly_unlocked_progress_reward():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    progress = (
        MODE_DAILY_QUESTS,
        STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    )
    opened_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),))
    opened_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),))
    progress_a = snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    progress_b = snapshot(5, 3.6, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    still_progress = snapshot(6, 4.0, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    settled_a = snapshot(7, 4.2, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    settled_b = snapshot(8, 4.8, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    lobby_a = snapshot(9, 5.0, base=SCREEN_LOBBY)
    lobby_b = snapshot(10, 5.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(opened_a, opened_b),
            stable_pair(progress_a, progress_b),
            [still_progress, settled_a, settled_b],
            stable_pair(lobby_a, lobby_b),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert not result.no_op
    assert result.claim_all_executed and result.claim_all_completed
    assert result.progress_reward_executed and result.progress_reward_completed
    assert result.event_count(DAILY_QUESTS_PROGRESS_REWARD_EXECUTED) == 1
    assert result.event_count(DAILY_QUESTS_PROGRESS_REWARD_COMPLETED) == 1
    assert actions == [
        OpenQuests(),
        ClaimAllDailyQuests(),
        ClaimDailyQuestsProgressReward(),
        CloseDailyQuests(),
    ]
    assert [call.after_sequence for call in observer.calls] == [1, 3, 5, 8]


def test_already_available_progress_reward_is_claimed_without_claim_all():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    progress = (
        MODE_DAILY_QUESTS,
        STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    )
    progress_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    progress_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    settled_a = snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    settled_b = snapshot(5, 3.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,), observations=(rows_observation(),))
    lobby_a = snapshot(6, 4.0, base=SCREEN_LOBBY)
    lobby_b = snapshot(7, 4.3, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(
        lobby,
        [
            stable_pair(progress_a, progress_b),
            stable_pair(settled_a, settled_b),
            stable_pair(lobby_a, lobby_b),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert not result.no_op
    assert not result.claim_all_executed
    assert result.progress_reward_executed and result.progress_reward_completed
    assert actions == [
        OpenQuests(),
        ClaimDailyQuestsProgressReward(),
        CloseDailyQuests(),
    ]


@pytest.mark.parametrize("progress", [False, True])
@pytest.mark.parametrize("recovers", [False, True])
def test_claim_tab_obscured_by_max_toast_waits_without_input(progress, recovers):
    # Galaxy Lord campaign: after a single claim, Quests remained resolved
    # at 43986..43988; the third frame lost Daily before its stable bound.
    lobby = snapshot(43963, 1.0, base=SCREEN_LOBBY)
    claim_status = (STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE
                    if progress else STATUS_DAILY_QUESTS_CLAIMABLE)
    opened = [snapshot(seq, time, base=SCREEN_QUESTS,
                       overlays=(MODE_DAILY_QUESTS, claim_status),
                       observations=(rows_observation(),))
              for seq, time in ((43964, 2.0), (43965, 2.3))]
    obscured = [snapshot(seq, time, base=SCREEN_QUESTS,
                         overlays=(MODE_DAILY_QUESTS,) if seq < 43988 else ())
                for seq, time in ((43986, 3.0), (43987, 3.1), (43988, 3.2))]
    recovered = [snapshot(seq, time, base=SCREEN_QUESTS,
                          overlays=(MODE_DAILY_QUESTS,),
                          observations=(rows_observation(),))
                 for seq, time in ((43989, 4.0), (43990, 4.6))]
    returned = [snapshot(seq, time, base=SCREEN_LOBBY)
                for seq, time in ((43991, 5.0), (43992, 5.3))]
    scripts = [opened, obscured + (recovered if recovers else [])]
    if recovers:
        scripts.append(returned)
    result, actions, _, observer = run_flow(lobby, scripts)
    claim = ClaimDailyQuestsProgressReward() if progress else ClaimAllDailyQuests()
    assert actions == [OpenQuests(), claim] + ([CloseDailyQuests()] if recovers else [])
    assert result.status is (FlowStatus.COMPLETED if recovers else FlowStatus.FAILED)
    assert result.progress_reward_completed is (progress and recovers)
    assert result.claim_all_completed is (not progress and recovers)
    assert observer.calls[1].after_sequence == 43965
    if not recovers:
        assert "no matching runtime snapshot" in result.error


@pytest.mark.parametrize("base,overlays,status", [
    (SCREEN_LOBBY, (), ResolutionStatus.RESOLVED),
    (SCREEN_QUESTS, ("overlay.foreign",), ResolutionStatus.RESOLVED),
    (None, (), ResolutionStatus.AMBIGUOUS),
])
def test_claim_wait_still_rejects_contradictory_context(base, overlays, status):
    incompatible = snapshot(10, 10.0, base=base, overlays=overlays, status=status,
                            base_candidates=(SCREEN_LOBBY, SCREEN_QUESTS)
                            if status is ResolutionStatus.AMBIGUOUS else ())
    assert DailyQuestsFlow._has_incompatible_daily_state(incompatible)
    assert not DailyQuestsFlow._is_daily_quests_settled(incompatible)


def test_progress_reward_claim_is_single_attempt_and_requires_disappearance():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    progress = (
        MODE_DAILY_QUESTS,
        STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    )
    progress_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))
    progress_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=progress, observations=(rows_observation(),))

    result, actions, _, _ = run_flow(
        lobby,
        [
            stable_pair(progress_a, progress_b),
            RuntimeWaitTimeout(
                after_sequence=3, timeout=8.0, last_snapshot=progress_b
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert actions.count(ClaimDailyQuestsProgressReward()) == 1
    assert ClaimAllDailyQuests() not in actions
    assert CloseDailyQuests() not in actions


@pytest.mark.parametrize(
    "claim_script",
    (
        RuntimeWaitTimeout(after_sequence=3, timeout=8.0, last_snapshot=None),
        [[snapshot(4, 4.0, base=SCREEN_LOBBY)]],
    ),
)
def test_claim_timeout_or_incompatible_state_fails_conservatively(claim_script):
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    opened = [
        snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),)),
        snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),)),
    ]
    script = claim_script[0] if isinstance(claim_script, list) else claim_script
    result, actions, events, _ = run_flow(lobby, [opened, script])

    assert result.status is FlowStatus.FAILED
    assert actions.count(ClaimAllDailyQuests()) == 1
    assert CloseDailyQuests() not in actions
    assert any(event == "daily_quests.failed" for event, _ in events)


def test_cancellation_during_claim_wait_returns_cancelled_without_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    opened = [
        snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),)),
        snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable, observations=(rows_observation(),)),
    ]
    result, actions, events, _ = run_flow(
        lobby,
        [opened, RuntimeWaitCancelled("cancelled")],
    )

    assert result.status is FlowStatus.CANCELLED
    assert actions == [OpenQuests(), ClaimAllDailyQuests()]
    assert any(event == "daily_quests.cancelled" for event, _ in events)


def tab_timeline(rows):
    """Completion times and capture ages are independent monotonic inputs."""
    now, cancelled = [100.], [False]
    initial = snapshot(10, 100., base=SCREEN_QUESTS)
    initial = replace(initial, frame=replace(initial.frame, source_id='quests-source'))
    observer = ScriptedObserver(initial, [])
    pending = iter(enumerate(rows, start=11))
    last = [initial]

    def observe():
        item = next(pending, None)
        if item is not None:
            seq, row = item
            now[0] = max(now[0], 100. + row['at'])
            obs = (rows_observation(),) if row.get('rows') else ()
            if row.get('loading'):
                obs += (Observation('activity.daily_quests_loading', 1., ObservationSource.LOCAL_CV),)
            overlays = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE) if row.get('daily') else ()
            current = snapshot(row.get('sequence', seq), 100. + row.get('captured', row['at']),
                base=None if row.get('status') is ResolutionStatus.AMBIGUOUS else row.get('base', SCREEN_QUESTS),
                overlays=overlays, status=row.get('status'), observations=obs,
                base_candidates=(SCREEN_QUESTS, SCREEN_LOBBY)
                    if row.get('status') is ResolutionStatus.AMBIGUOUS else ())
            last[0] = replace(current, frame=replace(current.frame,
                source_id=row.get('source', 'quests-source')))
            cancelled[0] = row.get('cancel', False)
        return last[0]

    observer.observe = observe
    actions, events = Actions(), Events()
    flow = DailyQuestsFlow(observer, actions, events,
        clock=lambda: now[0], sleeper=lambda t: now.__setitem__(0, now[0] + t),
        cancel_requested=lambda: cancelled[0])
    return SimpleNamespace(flow=flow, initial=initial, observer=observer,
        now=now, actions=actions, events=events)


def s2_observations():
    # S2 #882..886 offsets from first select_tab. 3005/3022 are
    # still Medal; 3034 is Daily + rows + loading after the fourth tap.
    # Capture ages/source are simulated: the bundle does not serialize
    # source_id or a capture-to-UTC bridge for these observations.
    return [dict(at=1.978239), dict(at=3.710036), dict(at=5.788249),
        dict(at=6.676966, captured=5.788249, daily=True, rows=True, loading=True)]


def test_s2_final_progress_gets_bounded_passive_tail_without_fifth_tap():
    h = tab_timeline(s2_observations() + [dict(at=7.9, daily=True, rows=True)])
    ready = h.flow._wait_for_daily_tab(h.initial)
    assert h.flow._is_daily_quests(ready) and h.flow._is_content_ready(ready)
    assert h.actions.items == [SelectDailyQuests()] * 4
    assert h.now[0] == pytest.approx(107.9)
    tail = next(f for e, f in h.events.items if e == 'daily_quests.tab_passive_tail')
    assert tail['loading'] and not tail['ready'] and tail['deadline'] == 108.
    assert tail['age'] == pytest.approx(.888717)


@pytest.mark.parametrize('last', [dict(at=7.9, daily=True, rows=True, loading=True),
    dict(at=8.1, daily=True, rows=True),
    dict(at=7.9, captured=5.7, daily=True, rows=True),
    dict(at=7.9, captured=9., daily=True, rows=True),
    dict(at=7.9, captured=0., daily=True, rows=True),
    dict(at=7.9, sequence=10, daily=True, rows=True)])
def test_s2_loading_deadline_stale_future_and_old_sequence_never_authorize_claim(last):
    h = tab_timeline(s2_observations() + [last])
    with pytest.raises(RuntimeWaitTimeout):
        h.flow._wait_for_daily_tab(h.initial)
    assert h.actions.items == [SelectDailyQuests()] * 4
    assert sum(e == 'daily_quests.tab_passive_tail' for e, _ in h.events.items) == 1
    assert h.now[0] <= 108.1


@pytest.mark.parametrize('change', [dict(base=SCREEN_LOBBY),
    dict(status=ResolutionStatus.AMBIGUOUS), dict(daily=False), dict(source='new-source')])
def test_s2_contradictory_tail_aborts_without_retry(change):
    last = dict(at=7.8, daily=True, rows=True)
    last.update(change)
    h = tab_timeline(s2_observations() + [last])
    with pytest.raises(RuntimeWaitAborted):
        h.flow._wait_for_daily_tab(h.initial)
    assert h.actions.items == [SelectDailyQuests()] * 4


@pytest.mark.parametrize('change', [dict(rows=False), dict(daily=False),
    dict(captured=4.), dict(captured=9.), dict(source=None)])
def test_s2_tail_requires_positive_fresh_progress_from_same_source(change):
    rows = s2_observations()
    rows[-1].update(change)
    h = tab_timeline(rows)
    with pytest.raises(RuntimeWaitAborted if 'source' in change else RuntimeWaitTimeout):
        h.flow._wait_for_daily_tab(h.initial)
    assert not any(e == 'daily_quests.tab_passive_tail' for e, _ in h.events.items)
    assert h.actions.items == [SelectDailyQuests()] * 4


def test_s2_tab_already_visible_suppresses_taps_through_unknown_and_late_readiness():
    h = tab_timeline([dict(at=1., daily=True, loading=True),
        dict(at=2., base=None), dict(at=3.),
        dict(at=6.5, daily=True, rows=True)])
    ready = h.flow._wait_for_daily_tab(h.initial)
    assert h.flow._is_content_ready(ready)
    assert h.now[0] == 106.5 and h.actions.items == [SelectDailyQuests()]


def test_s2_recent_loading_progress_can_wait_passively_across_a_repeated_frame():
    h = tab_timeline([dict(at=5.8, daily=True, rows=True, loading=True),
        dict(at=6.8, captured=5.8, sequence=11, daily=True, rows=True, loading=True),
        dict(at=7.8, daily=True, rows=True)])
    assert h.flow._is_content_ready(h.flow._wait_for_daily_tab(h.initial))
    assert h.now[0] == pytest.approx(107.8)
    assert h.actions.items == [SelectDailyQuests()]


@pytest.mark.parametrize('cancel_at', [6.676966, 7.8])
def test_s2_cancellation_precedes_recovery_and_claim(cancel_at):
    rows = s2_observations() + [dict(at=7.8, daily=True, rows=True)]
    next(r for r in rows if r['at'] == cancel_at)['cancel'] = True
    h = tab_timeline(rows)
    with pytest.raises(RuntimeWaitCancelled):
        h.flow._wait_for_daily_tab(h.initial)
    assert h.actions.items == [SelectDailyQuests()] * 4


def test_s2_parent_budget_cannot_be_extended_by_progress():
    from bot.operation_control import OperationControl, OperationBudgetExpired, control_scope
    h = tab_timeline(s2_observations() + [dict(at=7.8, daily=True, rows=True)])
    with control_scope(OperationControl(deadline=107., clock=lambda: h.now[0])):
        with pytest.raises(OperationBudgetExpired):
            h.flow._wait_for_daily_tab(h.initial)
    assert h.actions.items == [SelectDailyQuests()] * 4


def test_s2_fast_path_keeps_one_tap_one_observation_and_one_second():
    h = tab_timeline([dict(at=1., daily=True, rows=True)])
    assert h.flow._is_content_ready(h.flow._wait_for_daily_tab(h.initial))
    assert h.actions.items == [SelectDailyQuests()] and h.now[0] == 101.
    assert not any(e == 'daily_quests.tab_passive_tail' for e, _ in h.events.items)


@pytest.mark.parametrize('recovers', [True, False])
def test_s2_full_flow_claims_only_after_loading_clears(recovers):
    h = tab_timeline(s2_observations() + [dict(at=7.9, daily=True, rows=True,
        loading=not recovers)])
    lobby = snapshot(1, 99., base=SCREEN_LOBBY)
    # The existing open/claim/close waits retain their contracts. Only the
    # selection observations and their processing times reproduce S2.
    h.flow._initial_base = lambda seed: lobby
    h.observer.scripts = [[snapshot(9, 99.7, base=SCREEN_QUESTS), h.initial],
        [snapshot(20, 108., base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,)),
         snapshot(21, 108.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))],
        [snapshot(22, 109., base=SCREEN_LOBBY), snapshot(23, 109.3, base=SCREEN_LOBBY)]]
    dispatched = []
    execute = h.actions.execute
    def record(action, geometry):
        dispatched.append((type(action), h.now[0]))
        execute(action, geometry)
    h.actions.execute = record
    result = h.flow.run()
    assert result.status is (FlowStatus.COMPLETED if recovers else FlowStatus.FAILED)
    claims = [at for action, at in dispatched if action is ClaimAllDailyQuests]
    assert claims == ([107.9] if recovers else [])
    assert h.actions.items.count(SelectDailyQuests()) == 4
    assert h.actions.items.count(CloseDailyQuests()) == int(recovers)
