"""Precondition snapshot handoff: reuse verified evidence as flow initial.

Covers the single allowed optimization: the successful ensure result
carries the exact RuntimeSnapshot its requirement was verified on, and
opted-in flows may consume it instead of a fresh initial observe().
Fallback to observe() must preserve baseline behavior exactly.
"""

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_FRIENDS,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
)
from bot.component_contracts import (
    ComponentRequirement,
    QUICK_MENU_ACCESS_REQUIREMENT,
)
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.flow_contracts import (
    FlowContract,
    FlowResult,
    FlowScope,
    FlowStatus,
    run_flow_with_optional_seed,
)
from bot.observations import ObservationBatch
from bot.preconditions import EnsureOutcome, EnsureResult, MinimalPreconditionEnsurer
from bot.prepared_activity import PreparedActivity
from bot.rotation import RotationOutcome, RotationResult
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import CloseFriends, OpenFriends
from bot.send_stamina_flow import SendStaminaFlow
from bot.guild_check_in_flow import GuildCheckInFlow
from bot.mailbox_flow import MailboxFlow
from bot.daily_quests_flow import DailyQuestsFlow
from bot.session import SessionPlan, SessionRunner
from bot.state import ResolutionStatus, ResolvedState


LOBBY_REQUIREMENT = ComponentRequirement.exact_state(SCREEN_LOBBY)
GUILD_REQUIREMENT = ComponentRequirement.exact_state(SCREEN_GUILD)


def make_snapshot(sequence, timestamp, *, base, overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def lobby_snapshot(sequence=100, timestamp=100.0):
    return make_snapshot(sequence, timestamp, base=SCREEN_LOBBY)


def friends_snapshot(sequence, timestamp, *, daily_active):
    overlays = (
        (STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,) if daily_active else ()
    )
    return make_snapshot(
        sequence, timestamp, base=SCREEN_FRIENDS, overlays=overlays
    )


def guild_snapshot(sequence, timestamp, *, completed):
    overlays = (
        (STATUS_GUILD_ATTENDANCE_COMPLETED,)
        if completed
        else (STATUS_GUILD_ATTENDANCE_ACTIVE,)
    )
    return make_snapshot(
        sequence, timestamp, base=SCREEN_GUILD, overlays=overlays
    )


class CountingObserver:
    """Scripted observer counting fresh observe() calls."""

    def __init__(self, initial, scripts=()):
        self.initial = initial
        self.scripts = list(scripts)
        self.observe_calls = 0
        self.wait_calls = []

    def observe(self):
        self.observe_calls += 1
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
        self.wait_calls.append((after_sequence, stable_for))
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for item in script:
            last = item
            assert item.sequence > after_sequence
            if cancel_requested is not None and cancel_requested():
                raise RuntimeWaitCancelled("cancelled")
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            if condition(item):
                if stable_since is None:
                    stable_since = item.timestamp
                if item.timestamp - stable_since >= stable_for:
                    return item
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
        self.geometries = []

    def execute(self, action, geometry):
        self.items.append(action)
        self.geometries.append(geometry)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append(event)


def stable_pair(first, second):
    return [first, second]


# --- MinimalPreconditionEnsurer evidence transport ---


def test_already_satisfied_carries_entry_snapshot():
    seed = lobby_snapshot()
    ensurer = MinimalPreconditionEnsurer(lambda: (SCREEN_LOBBY, seed))

    ensured = ensurer.ensure(LOBBY_REQUIREMENT)

    assert ensured.outcome is EnsureOutcome.ALREADY_SATISFIED
    assert ensured.snapshot is seed


def test_legacy_string_adapter_carries_no_snapshot():
    ensurer = MinimalPreconditionEnsurer(lambda: SCREEN_LOBBY)

    ensured = ensurer.ensure(LOBBY_REQUIREMENT)

    assert ensured.succeeded
    assert ensured.snapshot is None


def test_navigation_carries_final_snapshot_never_before():
    before = lobby_snapshot(10, 10.0)
    after = guild_snapshot(20, 20.0, completed=True)
    entries = [(SCREEN_LOBBY, before), (SCREEN_GUILD, after)]
    ensurer = MinimalPreconditionEnsurer(
        lambda: entries.pop(0),
        navigate_lobby_to_guild=lambda: True,
    )

    ensured = ensurer.ensure(GUILD_REQUIREMENT)

    assert ensured.outcome is EnsureOutcome.NORMALIZED
    assert ensured.snapshot is after


def test_failed_ensure_carries_no_snapshot():
    ensurer = MinimalPreconditionEnsurer(lambda: (None, None))

    ensured = ensurer.ensure(GUILD_REQUIREMENT)

    assert not ensured.succeeded
    assert ensured.snapshot is None


def test_current_satisfies_any_stays_boolean_with_tuple_adapter():
    seed = lobby_snapshot()
    ensurer = MinimalPreconditionEnsurer(lambda: (SCREEN_LOBBY, seed))

    assert ensurer.current_satisfies_any((LOBBY_REQUIREMENT,)) is True
    assert ensurer.current_satisfies_any((GUILD_REQUIREMENT,)) is False


# --- run_flow_with_optional_seed helper ---


def test_seed_none_uses_plain_run():
    calls = []
    flow = SimpleNamespace(
        run=lambda: calls.append("run") or FlowResult(FlowStatus.COMPLETED),
        run_with_initial=lambda snapshot: calls.append("seeded"),
    )

    result = run_flow_with_optional_seed(flow, None)

    assert calls == ["run"]
    assert result.status is FlowStatus.COMPLETED


def test_plain_flow_ignores_snapshot():
    calls = []
    seed = lobby_snapshot()
    flow = SimpleNamespace(
        run=lambda: calls.append("run") or FlowResult(FlowStatus.COMPLETED),
    )

    result = run_flow_with_optional_seed(flow, seed)

    assert calls == ["run"]
    assert result.status is FlowStatus.COMPLETED


def test_opt_in_flow_receives_snapshot():
    received = []
    seed = lobby_snapshot()
    flow = SimpleNamespace(
        run=lambda: pytest.fail("must use the seed"),
        run_with_initial=lambda snapshot: received.append(snapshot)
        or FlowResult(FlowStatus.COMPLETED),
    )

    run_flow_with_optional_seed(flow, seed)

    assert received == [seed]


# --- SendStamina: seeded initial skips the global Lobby re-observe ---


def send_stamina_noop_scripts():
    return [
        stable_pair(
            friends_snapshot(101, 101.0, daily_active=False),
            friends_snapshot(102, 101.3, daily_active=False),
        ),
        stable_pair(
            lobby_snapshot(103, 102.0),
            lobby_snapshot(104, 102.3),
        ),
    ]


def test_send_stamina_seed_skips_initial_observe_and_anchors_on_seed():
    seed = lobby_snapshot(100, 100.0)
    observer = CountingObserver(lobby_snapshot(1, 1.0), send_stamina_noop_scripts())
    actions = Actions()
    flow = SendStaminaFlow(observer, actions, Events())

    result = flow.run_with_initial(seed)

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op and result.daily_completed
    assert observer.observe_calls == 0
    assert actions.items == [OpenFriends(), CloseFriends()]
    assert actions.geometries[0] is seed.geometry
    assert observer.wait_calls[0][0] == seed.sequence


def test_send_stamina_seed_matches_baseline_outcome():
    scripts = lambda: send_stamina_noop_scripts()  # noqa: E731
    seed = lobby_snapshot(100, 100.0)

    seeded = SendStaminaFlow(
        CountingObserver(lobby_snapshot(1, 1.0), scripts()), Actions(), Events()
    ).run_with_initial(seed)
    baseline = SendStaminaFlow(
        CountingObserver(lobby_snapshot(100, 100.0), scripts()),
        Actions(),
        Events(),
    ).run()

    assert (seeded.status, seeded.no_op, seeded.daily_completed) == (
        baseline.status,
        baseline.no_op,
        baseline.daily_completed,
    )


def test_send_stamina_unusable_seed_falls_back_to_observe():
    bad_seed = friends_snapshot(50, 50.0, daily_active=False)
    observer = CountingObserver(lobby_snapshot(100, 100.0), send_stamina_noop_scripts())
    flow = SendStaminaFlow(observer, Actions(), Events())

    result = flow.run_with_initial(bad_seed)

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert observer.observe_calls == 1


def test_send_stamina_none_seed_behaves_like_run():
    observer = CountingObserver(lobby_snapshot(100, 100.0), send_stamina_noop_scripts())
    flow = SendStaminaFlow(observer, Actions(), Events())

    result = flow.run_with_initial(None)

    assert result.status is FlowStatus.COMPLETED
    assert observer.observe_calls == 1


# --- GuildCheckIn: seeded Guild evidence ---


def test_guild_completed_seed_noop_without_observe():
    seed = guild_snapshot(200, 200.0, completed=True)
    observer = CountingObserver(guild_snapshot(1, 1.0, completed=True))
    flow = GuildCheckInFlow(observer, Actions(), Events())

    result = flow.run_with_initial(seed)

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op and result.attendance_completed
    assert observer.observe_calls == 0


def test_guild_active_seed_taps_and_anchors_on_seed():
    seed = guild_snapshot(200, 200.0, completed=False)
    completed_pair = stable_pair(
        guild_snapshot(201, 201.0, completed=True),
        guild_snapshot(202, 201.8, completed=True),
    )
    observer = CountingObserver(guild_snapshot(1, 1.0, completed=True))
    completion = CountingObserver(
        guild_snapshot(1, 1.0, completed=True), [completed_pair]
    )
    actions = Actions()
    flow = GuildCheckInFlow(
        observer, actions, Events(), completion_observer=completion
    )

    result = flow.run_with_initial(seed)

    assert result.status is FlowStatus.COMPLETED
    assert result.tap_executed and result.attendance_completed
    assert observer.observe_calls == 0
    assert completion.wait_calls[0][0] == seed.sequence


def test_guild_unusable_seed_falls_back_to_observe():
    observer = CountingObserver(guild_snapshot(300, 300.0, completed=True))
    flow = GuildCheckInFlow(observer, Actions(), Events())

    result = flow.run_with_initial(lobby_snapshot(50, 50.0))

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert observer.observe_calls == 1


# --- Mailbox / Daily: initial Lobby seed ---


def test_mailbox_initial_lobby_consumes_clean_seed():
    seed = lobby_snapshot(100, 100.0)
    observer = CountingObserver(lobby_snapshot(1, 1.0))
    flow = MailboxFlow(observer, Actions(), Events())

    assert flow._initial_lobby(seed) is seed
    assert observer.observe_calls == 0


def test_mailbox_initial_lobby_falls_back_on_other_context():
    observer = CountingObserver(lobby_snapshot(100, 100.0))
    flow = MailboxFlow(observer, Actions(), Events())

    initial = flow._initial_lobby(friends_snapshot(50, 50.0, daily_active=False))

    assert initial.sequence == 100
    assert observer.observe_calls == 1


def test_daily_initial_lobby_consumes_clean_seed():
    seed = lobby_snapshot(100, 100.0)
    observer = CountingObserver(lobby_snapshot(1, 1.0))
    flow = DailyQuestsFlow(observer, Actions(), Events())

    assert flow._initial_lobby(seed) is seed
    assert observer.observe_calls == 0


def test_daily_initial_lobby_falls_back_on_other_context():
    observer = CountingObserver(lobby_snapshot(100, 100.0))
    flow = DailyQuestsFlow(observer, Actions(), Events())

    initial = flow._initial_lobby(guild_snapshot(50, 50.0, completed=True))

    assert initial.sequence == 100
    assert observer.observe_calls == 1


# --- SessionRunner seeding ---


@dataclass
class SessionEvents:
    items: list

    def record(self, event, **fields):
        self.items.append(event)


def lobby_contract():
    return FlowContract(LOBBY_REQUIREMENT, (LOBBY_REQUIREMENT,))


def opt_in_flow(name, result, trace):
    def run():
        trace.append(f"{name}.run")
        return result

    def run_with_initial(snapshot):
        trace.append(f"{name}.run_with_initial:{snapshot.sequence}")
        return result

    return SimpleNamespace(
        name=name,
        scope=FlowScope.PER_CHARACTER,
        contract=lobby_contract(),
        run=run,
        run_with_initial=run_with_initial,
    )


def plain_flow(name, result, trace):
    def run():
        trace.append(f"{name}.run")
        return result

    return SimpleNamespace(
        name=name,
        scope=FlowScope.PER_CHARACTER,
        contract=lobby_contract(),
        run=run,
    )


def lobby_rotation(trace):
    from bot.component_contracts import ComponentContract

    return SimpleNamespace(
        character_count=1,
        contract=ComponentContract(
            QUICK_MENU_ACCESS_REQUIREMENT,
            (LOBBY_REQUIREMENT,),
        ),
        advance=lambda: trace.append("rotation.advance")
        or RotationResult(RotationOutcome.SUCCESS),
    )


def session_runner(events, entries, flows, *, trace, eligibility=(), cancel=lambda: False):
    def current_context():
        context, _snapshot = entries.pop(0)
        return context, _snapshot

    return SessionRunner(
        SessionPlan(
            1,
            tuple(flows),
            lobby_rotation(trace),
            eligibility=tuple(eligibility),
        ),
        preconditions=MinimalPreconditionEnsurer(current_context),
        events=events,
        cancel_requested=cancel,
    )


def test_session_runner_seeds_opt_in_flow_and_keeps_events():
    trace = []
    seed = lobby_snapshot(10, 10.0)
    entries = [
        (SCREEN_LOBBY, seed),
        (SCREEN_LOBBY, lobby_snapshot(11, 11.0)),
        (SCREEN_LOBBY, lobby_snapshot(12, 12.0)),
        (SCREEN_LOBBY, lobby_snapshot(13, 13.0)),
    ]
    events = SessionEvents([])
    flow = opt_in_flow("seeded", FlowResult(FlowStatus.COMPLETED), trace)
    runner = session_runner(events, entries, [flow], trace=trace)

    result = runner.run()

    assert result.status.value == "completed"
    assert trace == ["seeded.run_with_initial:10", "rotation.advance"]
    assert "flow.started" in events.items
    assert "flow.completed" in events.items
    assert "session.completed" in events.items


def test_session_runner_skips_seed_when_eligibility_present():
    trace = []
    seed = lobby_snapshot(10, 10.0)
    entries = [(SCREEN_LOBBY, lobby_snapshot(20 + i, 20.0 + i)) for i in range(6)]
    entries[0] = (SCREEN_LOBBY, seed)
    events = SessionEvents([])

    class Check:
        def evaluate(self):
            return EligibilityResult(EligibilityStatus.ELIGIBLE, "due")

    flow = opt_in_flow("guarded", FlowResult(FlowStatus.COMPLETED), trace)
    runner = session_runner(events, entries, [flow], trace=trace, eligibility=[Check()])

    result = runner.run()

    assert result.status.value == "completed"
    assert trace == ["guarded.run", "rotation.advance"]


def test_session_runner_skips_seed_for_prepared_activity():
    trace = []
    seed = lobby_snapshot(10, 10.0)
    entries = [(SCREEN_LOBBY, lobby_snapshot(20 + i, 20.0 + i)) for i in range(7)]
    entries[0] = (SCREEN_LOBBY, seed)
    events = SessionEvents([])
    zone = SimpleNamespace(
        entry_requirement=LOBBY_REQUIREMENT,
        hub_requirement=LOBBY_REQUIREMENT,
        enter=lambda: FlowResult(FlowStatus.COMPLETED),
        leave=lambda: FlowResult(FlowStatus.COMPLETED),
    )

    @dataclass(frozen=True)
    class SeededActivity(PreparedActivity):
        def run_with_initial(self, snapshot):
            trace.append("activity.run_with_initial")
            return FlowResult(FlowStatus.COMPLETED)

    activity = SeededActivity(
        name="prepared", zone=zone, execute=lambda: trace.append("activity.run")
        or FlowResult(FlowStatus.COMPLETED),
    )
    runner = session_runner(events, entries, [activity], trace=trace)

    result = runner.run()

    assert result.status.value == "completed"
    assert "activity.run" in trace
    assert "activity.run_with_initial" not in trace


# --- ProductiveRuntime (GUI selected-flows runner) ---


def productive_runtime(monkeypatch, flow, ensured):
    from bot.event_log import RuntimeEventStream
    from bot.productive_runtime import CancellationToken, ProductiveRuntime

    runtime = ProductiveRuntime(
        config=object(), observer=object(), actions=object(), facts=object(),
        auto_battle=object(), socket_relief=object(),
        equipment_combine_relief=object(), pet_summon_space_relief=object(),
        events=RuntimeEventStream(), cancel_token=CancellationToken(),
    )
    monkeypatch.setattr(runtime, "build_flow", lambda definition: flow)
    monkeypatch.setattr(
        runtime,
        "build_preconditions",
        lambda: SimpleNamespace(
            ensure=lambda requirement: ensured,
            current_satisfies_any=lambda requirements: True,
        ),
    )
    return runtime


def flow_namespace(trace, *, opt_in):
    namespace = SimpleNamespace(
        name="candidate",
        contract=SimpleNamespace(
            precondition=LOBBY_REQUIREMENT,
            successful_postconditions=(LOBBY_REQUIREMENT,),
        ),
        run=lambda: trace.append("run") or FlowResult(FlowStatus.COMPLETED),
    )
    if opt_in:
        def run_with_initial(snapshot):
            trace.append(f"seeded:{snapshot.sequence}")
            return FlowResult(FlowStatus.COMPLETED)

        namespace.run_with_initial = run_with_initial
    return namespace


def test_run_flows_once_seeds_opt_in_flow(monkeypatch):
    trace = []
    seed = lobby_snapshot(10, 10.0)
    flow = flow_namespace(trace, opt_in=True)
    ensured = EnsureResult(
        EnsureOutcome.ALREADY_SATISFIED, LOBBY_REQUIREMENT,
        SCREEN_LOBBY, SCREEN_LOBBY, snapshot=seed,
    )
    runtime = productive_runtime(monkeypatch, flow, ensured)

    result = runtime.run_flow(SimpleNamespace(id="candidate"))

    assert result.status is FlowStatus.COMPLETED
    assert trace == ["seeded:10"]


def test_run_flows_once_falls_back_for_plain_flow(monkeypatch):
    trace = []
    flow = flow_namespace(trace, opt_in=False)
    ensured = EnsureResult(
        EnsureOutcome.ALREADY_SATISFIED, LOBBY_REQUIREMENT,
        SCREEN_LOBBY, SCREEN_LOBBY, snapshot=lobby_snapshot(10, 10.0),
    )
    runtime = productive_runtime(monkeypatch, flow, ensured)

    result = runtime.run_flow(SimpleNamespace(id="candidate"))

    assert result.status is FlowStatus.COMPLETED
    assert trace == ["run"]


def test_run_flows_once_without_snapshot_runs_normally(monkeypatch):
    trace = []
    flow = flow_namespace(trace, opt_in=True)
    ensured = EnsureResult(
        EnsureOutcome.ALREADY_SATISFIED, LOBBY_REQUIREMENT,
        SCREEN_LOBBY, SCREEN_LOBBY,
    )
    runtime = productive_runtime(monkeypatch, flow, ensured)

    result = runtime.run_flow(SimpleNamespace(id="candidate"))

    assert result.status is FlowStatus.COMPLETED
    assert trace == ["run"]
