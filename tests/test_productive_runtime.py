from pathlib import Path

import pytest

import bot.productive_runtime as productive
from bot.event_log import RuntimeEventStream


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


def test_productive_composition_acquires_one_shared_graph_and_cleans_source(monkeypatch):
    source = Source()
    config = object()
    adb = Adb()
    events = RuntimeEventStream()
    observer = object()
    actions = object()
    facts = object()
    auto = object()
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

    with productive.open_productive_runtime(log_path="ignored.log") as runtime:
        assert runtime.config is config
        assert runtime.observer is observer
        assert runtime.actions is actions
        assert runtime.facts is facts
        assert runtime.auto_battle is auto
        assert source.entered and not source.exited

    assert source.exited


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
