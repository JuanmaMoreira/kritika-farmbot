from datetime import datetime, timezone

import pytest

from bot.event_log import EventLevel, RuntimeEvent, format_runtime_event
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_model import (
    FlowSelectionModel,
    GuiExecutionRequest,
    GuiProgress,
    SessionElapsedTimer,
    event_visible,
)


def runtime_event(level, event, component="session", **fields):
    return RuntimeEvent(
        datetime(2026, 8, 28, 14, 32, 15, 382000, tzinfo=timezone.utc),
        level,
        component,
        event,
        fields,
    )


def test_selection_is_populated_only_from_registry_and_defaults_active():
    model = FlowSelectionModel(DEFAULT_FLOW_REGISTRY)

    assert [(item.id, item.display_name) for item in model.options] == [
        (item.id, item.display_name) for item in DEFAULT_FLOW_REGISTRY.definitions
    ]
    assert model.active_ids == (
        "black_market",
        "world_boss",
        "daily_quests",
        "mailbox",
    )


def test_toggle_and_move_preserve_exact_active_order():
    model = FlowSelectionModel()

    model.move_up("world_boss")
    assert model.active_ids == (
        "world_boss",
        "black_market",
        "daily_quests",
        "mailbox",
    )
    model.set_enabled("world_boss", False)
    assert model.active_ids == ("black_market", "daily_quests", "mailbox")
    model.toggle("world_boss")
    assert model.active_ids == (
        "world_boss",
        "black_market",
        "daily_quests",
        "mailbox",
    )
    assert not model.move_up("world_boss")


def test_execution_request_validation():
    with pytest.raises(ValueError, match="exactly one"):
        GuiExecutionRequest.flow_once(("black_market", "world_boss"))
    with pytest.raises(ValueError, match="exactly one"):
        GuiExecutionRequest.flow_once(())
    with pytest.raises(ValueError, match="at least one"):
        GuiExecutionRequest.session((), 2)
    with pytest.raises(ValueError, match="positive integer"):
        GuiExecutionRequest.session(("black_market",), 0)


def test_session_timer_starts_at_zero_updates_monotonically_and_freezes_final_duration():
    now = [100.0]
    timer = SessionElapsedTimer(clock=lambda: now[0])

    assert timer.text == "00:00:00"
    assert timer.start() == "00:00:00"
    now[0] = 3761.9
    assert timer.update() == "01:01:01"
    assert timer.finish(3662.8) == "01:01:02"

    now[0] = 9000.0
    assert not timer.running
    assert timer.update() == "01:01:02"


def test_new_session_resets_a_previous_final_duration():
    now = [10.0]
    timer = SessionElapsedTimer(clock=lambda: now[0])
    timer.start()
    timer.finish(12.9)

    now[0] = 30.0
    assert timer.start() == "00:00:00"
    now[0] = 31.2
    assert timer.update() == "00:00:01"


def test_progress_is_directly_derived_from_runtime_events():
    progress = GuiProgress()

    progress.apply(runtime_event(
        EventLevel.INFO,
        "session.character.started",
        character_index=2,
        character_count=28,
    ))
    progress.apply(runtime_event(
        EventLevel.INFO,
        "flow.started",
        component="world_boss",
        flow="world_boss",
    ))
    progress.apply(runtime_event(
        EventLevel.DEBUG,
        "world_boss.wait.started",
        component="controlled_wait",
        timer_initial=60,
        expected_wait=65,
    ))

    assert progress.character == "2 / 28"
    assert progress.flow == "World Boss"
    assert progress.state == "Waiting"


def test_debug_filter_and_shared_formatter_include_timestamp_level_component_fields():
    debug_event = runtime_event(
        EventLevel.DEBUG,
        "transition.retry",
        component="transition",
        attempt=2,
    )
    info_event = runtime_event(EventLevel.INFO, "session.started", character_count=2)

    assert not event_visible(debug_event, debug=False)
    assert event_visible(debug_event, debug=True)
    assert event_visible(info_event, debug=False)
    rendered = format_runtime_event(debug_event)
    assert ":32:15.382" in rendered
    assert "DEBUG" in rendered and "transition" in rendered
    assert "attempt=2" in rendered
