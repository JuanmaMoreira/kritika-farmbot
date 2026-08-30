from pathlib import Path
from types import SimpleNamespace

import pytest

import bot.productive_runtime as productive
from bot.catalog import MENU_QUICK, SCREEN_LOBBY, SCREEN_WORLD_BOSS
from bot.event_log import RuntimeEventStream
from bot.productive_runtime import ProductiveRuntime
from bot.runtime_observer import RuntimeWaitTimeout
from bot.semantic_actions import OpenQuickMenu, SelectQuickMenuLobby
from bot.state import ResolutionStatus


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
        events=events,
        cancel_token=SimpleNamespace(is_requested=lambda: False),
    )


def test_productive_composition_acquires_one_shared_graph_and_cleans_source(monkeypatch):
    source = Source()
    config = object()
    adb = Adb()
    events = RuntimeEventStream()
    observer = object()
    actions = object()
    facts = object()
    auto = object()
    transition = object()
    tap_through = object()
    socket_relief = object()
    equipment_combine_relief = object()
    monkeypatch.setattr(productive, "build_runtime_event_stream", lambda *a, **k: events)
    monkeypatch.setattr(productive.RuntimeConfig, "from_env", lambda **kwargs: config)
    monkeypatch.setattr(productive, "build_adb_client", lambda value: adb)
    monkeypatch.setattr(productive, "build_frame_source", lambda *a, **k: source)
    monkeypatch.setattr(productive, "ActionExecutor", lambda value: actions)
    monkeypatch.setattr(productive, "build_default_perception", lambda root: object())
    monkeypatch.setattr(productive, "build_default_resolver", lambda: object())
    monkeypatch.setattr(productive, "RuntimeObserver", lambda *args: observer)
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

    with productive.open_productive_runtime(log_path="ignored.log") as runtime:
        assert runtime.config is config
        assert runtime.observer is observer
        assert runtime.actions is actions
        assert runtime.facts is facts
        assert runtime.auto_battle is auto
        assert runtime.socket_relief is socket_relief
        assert runtime.equipment_combine_relief is equipment_combine_relief
        assert source.entered and not source.exited

    assert source.exited


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
            return SimpleNamespace(succeeded=True, final_snapshot=final)

    monkeypatch.setattr(productive, "VerifiedTransition", lambda *args: Transition())

    assert runtime._navigate_to_lobby()
    assert [(name, action) for name, action, _, _ in calls] == [
        ("precondition.open_quick_menu", OpenQuickMenu()),
        ("precondition.select_lobby", SelectQuickMenuLobby()),
    ]
    assert runtime.build_preconditions().navigate_to_lobby is not None
