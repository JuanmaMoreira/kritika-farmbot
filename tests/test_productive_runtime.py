import json
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
from dataclasses import dataclass

import pytest

import bot.productive_runtime as productive
from bot.catalog import (
    MENU_QUICK,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
)
from bot.event_log import RuntimeEventStream
from bot.productive_runtime import ProductiveRuntime
from bot.runtime_observer import RuntimeWaitTimeout
from bot.semantic_actions import (
    ClosePets,
    OpenGuild,
    OpenPets,
    OpenQuickMenu,
    QuickMenuLayout,
    SelectQuickMenuGuild,
    SelectQuickMenuLobby,
)
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionOutcome


@pytest.fixture(autouse=True)
def isolated_failure_evidence(tmp_path, monkeypatch):
    evidence_type = productive.FailureEvidence
    monkeypatch.setattr(productive, "FailureEvidence", lambda root: evidence_type(tmp_path / "evidence"))


def _snapshot(sequence, *, status, base=None, overlays=()):
    return SimpleNamespace(
        sequence=sequence,
        state=SimpleNamespace(
            status=status,
            base_context=base,
            overlays=frozenset(overlays),
        ),
    )


class Observer:
    def __init__(self, initial, wait_result):
        self.initial = initial
        self.wait_result = wait_result
        self.wait_calls = []

    def observe(self):
        return self.initial

    def wait_until(self, predicate, **kwargs):
        self.wait_calls.append((predicate, kwargs))
        if isinstance(self.wait_result, Exception):
            raise self.wait_result
        return self.wait_result


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


class Source:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.exited = True


class Adb:
    def get_state(self):
        return "device"


def _runtime(observer, events):
    return ProductiveRuntime(
        config=object(),
        observer=observer,
        actions=object(),
        facts=object(),
        auto_battle=object(),
        socket_relief=object(),
        equipment_combine_relief=object(),
        pet_summon_space_relief=object(),
        events=events,
        cancel_token=SimpleNamespace(is_requested=lambda: False),
    )


@pytest.mark.parametrize("mode", ["recognized", "variants", "unknown", "exception", "initialization_exception"])
def test_session_identity_reuses_first_precondition_without_extra_observations(monkeypatch, mode):
    import numpy as np
    from bot.flow_contracts import FlowResult, FlowStatus
    from bot.ocr import OcrResult
    from bot.session import SessionRunner
    from bot.session_report import build_session_report
    from test_session import Flow, Rotation

    def execute(enabled):
        trace = []
        sequence = 0
        def observe():
            nonlocal sequence
            sequence += 1
            trace.append("observe")
            result = _snapshot(sequence, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
            result.frame = SimpleNamespace(image=np.zeros((400, 800, 3), np.uint8))
            return result
        runtime = _runtime(SimpleNamespace(observe=observe), Events())
        flows = tuple(Flow(name, [FlowResult(FlowStatus.COMPLETED)] * 2, trace)
                      for name in ("first", "second"))
        rotation = Rotation(2, trace)
        monkeypatch.setattr(runtime, "build_flows", lambda definitions: flows)
        monkeypatch.setattr(runtime, "build_rotation", lambda count: rotation)
        engine = Mock()
        if mode == "exception":
            engine.recognize.side_effect = RuntimeError("OCR failure")
        elif mode == "variants":
            engine.recognize.side_effect = [OcrResult("DRAKEN-BK", .99), OcrResult("DRAKENDB", .99)]
        else:
            engine.recognize.side_effect = [
                OcrResult("Drakenn25" if mode == "recognized" else "unlisted", .99),
                OcrResult("DRAKEN四BD" if mode == "recognized" else "unlisted", .99),
            ]
        def make_engine():
            if mode == "initialization_exception":
                raise RuntimeError("backend unavailable")
            return engine
        monkeypatch.setattr(productive, "RapidOcrEngine", make_engine)
        def runner(*args, **kwargs):
            if not enabled:
                kwargs["character_context_factory"] = None
            return SessionRunner(*args, **kwargs)
        monkeypatch.setattr(productive, "SessionRunner", runner)
        result = runtime.run_session((), character_count=2)
        assert runtime._identity_snapshot is None
        assert runtime._identity_active is False
        assert engine.recognize.call_count == (2 if enabled and mode != "initialization_exception" else 0)
        return result, trace, runtime.events.items

    baseline, baseline_trace, baseline_events = execute(False)
    result, trace, events = execute(True)
    assert trace == baseline_trace
    assert trace.count("observe") == 12
    assert trace.count("rotation.advance") == 2
    assert [e for e, _ in events] == [e for e, _ in baseline_events]
    assert result.status == baseline.status
    report = build_session_report(result)
    assert [c.label for c in report.characters] == (
        ["Kaiserin", "Blade Dancer"] if mode == "recognized" else
        ["Berserker", "Demon Blade"] if mode == "variants" else ["Character 1", "Character 2"])


def test_identity_snapshot_cannot_leak_after_unknown_probe(monkeypatch):
    lobby = _snapshot(1, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    unknown = _snapshot(2, status=ResolutionStatus.UNKNOWN)
    observer = Observer(lobby, RuntimeWaitTimeout(timeout=1, after_sequence=2, last_snapshot=unknown))
    runtime = _runtime(observer, Events())
    runtime._identity_active = True
    assert runtime._current_clean_context() == SCREEN_LOBBY
    assert runtime._identity_snapshot is lobby
    observer.initial = unknown
    assert runtime._current_clean_context() is None
    assert runtime._identity_snapshot is None


def test_productive_composition_acquires_one_shared_graph_and_cleans_source(monkeypatch):
    source = Source()
    config = object()
    adb = Adb()
    events = RuntimeEventStream()
    observer = Mock()
    actions = object()
    facts = object()
    auto = object()
    transition = object()
    tap_through = object()
    socket_relief = object()
    equipment_combine_relief = object()
    pet_summon_space_relief = object()
    monkeypatch.setattr(productive, "build_runtime_event_stream", lambda *a, **k: events)
    monkeypatch.setattr(productive.RuntimeConfig, "from_env", lambda **kwargs: config)
    monkeypatch.setattr(productive, "build_adb_client", lambda value: adb)
    monkeypatch.setattr(productive, "build_frame_source", lambda *a, **k: source)
    monkeypatch.setattr(productive, "ActionExecutor", lambda value: actions)
    monkeypatch.setattr(productive, "build_default_perception", lambda root: object())
    monkeypatch.setattr(productive, "build_default_resolver", lambda: object())
    monkeypatch.setattr(productive, "RuntimeObserver", lambda *args, **kwargs: observer)
    monkeypatch.setattr(productive, "build_runtime_fact_reader", lambda value, events: facts)
    monkeypatch.setattr(productive, "AutoBattleDetector", lambda value: object())
    monkeypatch.setattr(productive, "AutoBattleEnsurer", lambda detector, action: auto)
    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: transition)
    monkeypatch.setattr(productive, "TapThroughAnimation", lambda *args: tap_through)
    monkeypatch.setattr(
        productive,
        "SocketInventoryRelief",
        lambda *args, **kwargs: socket_relief,
    )
    monkeypatch.setattr(
        productive,
        "EquipmentCombineRelief",
        lambda *args, **kwargs: equipment_combine_relief,
    )
    monkeypatch.setattr(
        productive,
        "PetSummonSpaceRelief",
        lambda *args, **kwargs: pet_summon_space_relief,
    )

    with productive.open_productive_runtime(log_path="ignored.log") as runtime:
        assert runtime.config is config
        assert runtime.observer is observer
        assert runtime.actions is actions
        assert runtime.facts is facts
        assert runtime.auto_battle is auto
        assert runtime.socket_relief is socket_relief
        assert runtime.equipment_combine_relief is equipment_combine_relief
        assert runtime.pet_summon_space_relief is pet_summon_space_relief
        assert source.entered and not source.exited

    assert source.exited
    observer.flush_analysis_metrics.assert_called_once_with()
    assert events.failure_evidence is None


def test_legacy_equipment_inventory_relief_name_has_no_compatibility_alias():
    assert not Path("bot/equipment_inventory_relief.py").exists()
    assert not hasattr(productive, "EquipmentInventoryRelief")


def test_runtime_configuration_failure_is_persisted_to_session_log(monkeypatch, tmp_path):
    path = tmp_path / "failed.log"

    def fail(**kwargs):
        raise ValueError("missing config")

    monkeypatch.setattr(productive.RuntimeConfig, "from_env", fail)

    with pytest.raises(ValueError, match="missing config"):
        with productive.open_productive_runtime(log_path=path):
            pass

    content = path.read_text(encoding="utf-8")
    assert '"event": "runtime.started"' in content
    assert '"event": "runtime.failed"' in content
    assert '"event": "runtime.closed"' in content
    failure = next(json.loads(line)["failure"] for line in content.splitlines()
                   if json.loads(line)["event"] == "runtime.failed")
    assert failure["evidence_ref"]
    assert failure["message"] == "missing config"
    assert len(list((tmp_path / "evidence").glob("failure_*/failure.json"))) == 1


def test_clean_context_probe_tolerates_transient_unresolved_frames_for_five_seconds():
    observer = Observer(
        _snapshot(17, status=ResolutionStatus.UNKNOWN),
        _snapshot(21, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY),
    )
    runtime = _runtime(observer, Events())

    assert runtime._current_clean_context() == SCREEN_LOBBY
    predicate, kwargs = observer.wait_calls[0]
    assert predicate(observer.wait_result)
    assert kwargs == {
        "after_sequence": 17,
        "timeout": 5.0,
        "stable_for": 0.25,
        "cancel_requested": runtime.cancel_requested,
    }


@pytest.mark.parametrize(
    ("base", "overlays"),
    (
        (SCREEN_PETS_MANAGE, ()),
        (SCREEN_PETS_MANAGE, (STATUS_PET_SUMMON_DAILY_ACTIVE,)),
        (
            SCREEN_PET_SUMMON,
            (STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
        ),
    ),
)
def test_clean_context_probe_accepts_stable_pet_flow_outputs(base, overlays):
    pet = _snapshot(
        1,
        status=ResolutionStatus.RESOLVED,
        base=base,
        overlays=overlays,
    )
    observer = Observer(pet, pet)

    assert _runtime(observer, Events())._current_clean_context() == base
    assert observer.wait_calls == []


def test_clean_context_probe_accepts_guild_attendance_with_daily_badge():
    guild = _snapshot(
        17,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays={
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        },
    )
    runtime = _runtime(Observer(guild, guild), Events())

    assert runtime._current_clean_context() == SCREEN_GUILD


def test_clean_context_probe_rejects_daily_badge_without_attendance_state():
    guild = _snapshot(
        17,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays={STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE},
    )

    assert not productive._is_clean_base(guild, SCREEN_GUILD)


def test_clean_context_probe_timeout_records_last_observed_state():
    latest = _snapshot(
        29,
        status=ResolutionStatus.AMBIGUOUS,
        base=SCREEN_LOBBY,
        overlays={"popup.example"},
    )
    observer = Observer(
        _snapshot(24, status=ResolutionStatus.UNKNOWN),
        RuntimeWaitTimeout(
            after_sequence=24,
            timeout=5.0,
            last_snapshot=latest,
        ),
    )
    events = Events()
    runtime = _runtime(observer, events)

    assert runtime._current_clean_context() is None
    assert events.items == [
        (
            "runtime.context_probe_timeout",
            {
                "timeout": 5.0,
                "after_sequence": 24,
                "last_sequence": 29,
                "resolution_status": ResolutionStatus.AMBIGUOUS.value,
                "base_context": SCREEN_LOBBY,
                "overlays": ["popup.example"],
            },
        )
    ]


def test_productive_precondition_normalizes_world_boss_to_lobby(monkeypatch):
    world_boss = _snapshot(
        1, status=ResolutionStatus.RESOLVED, base=SCREEN_WORLD_BOSS
    )
    quick_menu = _snapshot(
        2, status=ResolutionStatus.UNKNOWN, overlays={MENU_QUICK}
    )
    lobby = _snapshot(3, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    observer = Observer(world_boss, lobby)
    runtime = _runtime(observer, Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action, before, kwargs))
            final = quick_menu if len(calls) == 1 else lobby
            assert kwargs["expected"](final)
            assert kwargs["precondition"](before)
            return SimpleNamespace(
                succeeded=True, final_snapshot=final,
                action_source_snapshot=before if len(calls) == 1 else None,
                recovery_after_action=False,
            )

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_lobby()
    assert [(name, action) for name, action, _, _ in calls] == [
        ("precondition.open_quick_menu", OpenQuickMenu()),
        ("precondition.select_lobby", SelectQuickMenuLobby()),
    ]
    assert runtime.build_preconditions().navigate_to_lobby is not None


def test_productive_precondition_navigates_world_boss_via_quick_menu_to_guild(monkeypatch):
    world_boss = _snapshot(
        1, status=ResolutionStatus.RESOLVED, base=SCREEN_WORLD_BOSS
    )
    quick_menu = _snapshot(
        2, status=ResolutionStatus.UNKNOWN, overlays={MENU_QUICK}
    )
    guild = _snapshot(
        3,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays={
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        },
    )
    observer = Observer(world_boss, guild)
    runtime = _runtime(observer, Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action, before, kwargs))
            final = quick_menu if len(calls) == 1 else guild
            assert kwargs["expected"](final)
            assert kwargs["precondition"](before)
            assert not kwargs["abort_if"](final)
            return SimpleNamespace(
                succeeded=True, final_snapshot=final,
                action_source_snapshot=before if len(calls) == 1 else None,
                recovery_after_action=False,
            )

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_guild()
    assert [(name, action) for name, action, _, _ in calls] == [
        ("precondition.open_quick_menu", OpenQuickMenu()),
        (
            "precondition.select_guild",
            SelectQuickMenuGuild(QuickMenuLayout.SHIFTED),
        ),
    ]
    assert runtime.build_preconditions().navigate_to_guild is not None


@pytest.mark.parametrize(
    ("origin", "overlays"),
    (
        (SCREEN_PETS_MANAGE, (STATUS_PET_SUMMON_DAILY_ACTIVE,)),
        (
            SCREEN_PET_SUMMON,
            (
                STATUS_PET_EPIC_AVAILABLE,
                STATUS_PET_PREMIUM_GOLD,
                STATUS_PET_SUMMON_DAILY_ACTIVE,
            ),
        ),
    ),
)
def test_productive_precondition_navigates_pet_exit_directly_to_guild(
    monkeypatch, origin, overlays
):
    pet = _snapshot(
        1,
        status=ResolutionStatus.RESOLVED,
        base=origin,
        overlays=overlays,
    )
    quick_menu = _snapshot(
        2, status=ResolutionStatus.UNKNOWN, overlays={MENU_QUICK}
    )
    guild = _snapshot(
        3,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays={
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        },
    )
    runtime = _runtime(Observer(pet, guild), Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action))
            final = quick_menu if len(calls) == 1 else guild
            assert kwargs["precondition"](before)
            assert kwargs["expected"](final)
            return SimpleNamespace(
                succeeded=True, final_snapshot=final,
                action_source_snapshot=before if len(calls) == 1 else None,
                recovery_after_action=False,
            )

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_guild()
    assert calls == [
        ("precondition.open_quick_menu", OpenQuickMenu()),
        (
            "precondition.select_guild",
            SelectQuickMenuGuild(QuickMenuLayout.SHIFTED),
        ),
    ]


def test_productive_precondition_opens_pet_manage_from_lobby(monkeypatch):
    lobby = _snapshot(1, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    manage = _snapshot(
        2,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_PETS_MANAGE,
        overlays={STATUS_PET_SUMMON_DAILY_ACTIVE},
    )
    runtime = _runtime(Observer(lobby, manage), Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action))
            assert kwargs["precondition"](before)
            assert kwargs["expected"](manage)
            return SimpleNamespace(succeeded=True, final_snapshot=manage)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_pets_manage()
    assert calls == [("precondition.open_pets", OpenPets())]
    assert runtime.build_preconditions().navigate_to_pets_manage is not None


@pytest.mark.parametrize(
    ("origin", "overlays"),
    (
        (SCREEN_PETS_MANAGE, ()),
        (
            SCREEN_PET_SUMMON,
            (STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
        ),
    ),
)
def test_productive_precondition_closes_pet_exit_directly_to_lobby(
    monkeypatch, origin, overlays
):
    pet = _snapshot(
        1,
        status=ResolutionStatus.RESOLVED,
        base=origin,
        overlays=overlays,
    )
    lobby = _snapshot(2, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    runtime = _runtime(Observer(pet, lobby), Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action))
            assert kwargs["precondition"](before)
            assert kwargs["expected"](lobby)
            return SimpleNamespace(succeeded=True, final_snapshot=lobby)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_lobby()
    assert calls == [("precondition.close_pets", ClosePets())]


def test_productive_precondition_navigates_lobby_directly_to_verified_guild(
    monkeypatch,
):
    lobby = _snapshot(1, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    guild = _snapshot(
        2,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays={
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        },
    )
    runtime = _runtime(Observer(lobby, guild), Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append((name, action, before, kwargs))
            assert kwargs["expected"](guild)
            assert kwargs["precondition"](before)
            assert not kwargs["abort_if"](guild)
            return SimpleNamespace(succeeded=True, final_snapshot=guild)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_lobby_to_guild()
    assert [(name, action) for name, action, _, _ in calls] == [
        ("precondition.open_guild", OpenGuild()),
    ]
    assert runtime.build_preconditions().navigate_lobby_to_guild is not None


def test_quick_menu_guild_fallback_rejects_lobby_origin_without_input(monkeypatch):
    lobby = _snapshot(1, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    runtime = _runtime(Observer(lobby, lobby), Events())
    monkeypatch.setattr(
        productive,
        "VerifiedTransition",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not navigate")),
    )

    assert not runtime._navigate_to_guild()


def test_guild_navigation_rejects_unverified_destination(monkeypatch):
    lobby = _snapshot(1, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    observer = Observer(lobby, lobby)
    runtime = _runtime(observer, Events())
    calls = []

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append(name)
            assert not kwargs["expected"](lobby)
            return SimpleNamespace(succeeded=False, final_snapshot=lobby)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert not runtime._navigate_lobby_to_guild()
    assert calls == ["precondition.open_guild"]


@pytest.mark.parametrize("route", ["_navigate_to_lobby", "_navigate_to_guild"])
def test_productive_menu_discovery_without_action_anchor_never_selects_tile(
    monkeypatch, route,
):
    source = _snapshot(
        1, status=ResolutionStatus.RESOLVED, base=SCREEN_WORLD_BOSS,
    )
    menu = _snapshot(
        2, status=ResolutionStatus.UNKNOWN, overlays={MENU_QUICK},
    )
    runtime = _runtime(Observer(source, source), Events())
    calls = []

    @dataclass(frozen=True)
    class Result:
        outcome: VerifiedTransitionOutcome
        final_snapshot: object
        action_source_snapshot: object = None
        recovery_after_action: bool = False
        error: str | None = None

        @property
        def succeeded(self):
            return self.outcome is VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append(action)
            assert isinstance(action, OpenQuickMenu)
            return Result(VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, menu)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())
    assert not getattr(runtime, route)()
    assert calls == [OpenQuickMenu()]


def test_productive_foreign_resolved_menu_aborts_before_lobby_tile(monkeypatch):
    source = _snapshot(
        1, status=ResolutionStatus.RESOLVED, base=SCREEN_WORLD_BOSS,
    )
    foreign = _snapshot(
        2, status=ResolutionStatus.RESOLVED, base=SCREEN_GUILD,
        overlays={MENU_QUICK},
    )
    runtime = _runtime(Observer(source, source), Events())
    calls = []

    @dataclass(frozen=True)
    class Result:
        outcome: VerifiedTransitionOutcome
        final_snapshot: object
        action_source_snapshot: object
        recovery_after_action: bool = False
        error: str | None = None

        @property
        def succeeded(self):
            return self.outcome is VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT

    class Transition:
        def execute(self, name, action, before, **kwargs):
            calls.append(action)
            assert isinstance(action, OpenQuickMenu)
            assert not kwargs["expected"](foreign)
            assert kwargs["abort_if"](foreign)
            return Result(
                VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, foreign, source,
            )

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())
    assert not runtime._navigate_to_lobby()
    assert calls == [OpenQuickMenu()]
