import io
import json
from datetime import datetime, timezone

from bot.controlled_wait import ControlledWait
from bot.event_log import (
    ConsoleEventConsumer,
    EventLevel,
    JsonLineEventConsumer,
    RuntimeEventStream,
    build_runtime_event_stream,
)


class FakeTime:
    def __init__(self):
        self.current = 0.0

    def clock(self):
        return self.current

    def sleep(self, duration):
        self.current += duration


def test_stream_has_timestamp_level_component_fields_and_persistent_file(tmp_path):
    path = tmp_path / "session.log"
    captured = []
    stream = RuntimeEventStream(
        (captured.append, JsonLineEventConsumer(path)),
        now=lambda: datetime(2026, 8, 28, 12, 0, 0, 123000, tzinfo=timezone.utc),
    )

    stream.record("session.started", character_count=2)

    assert captured[0].level is EventLevel.INFO
    assert captured[0].component == "session"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["timestamp"] == "2026-08-28T12:00:00.123000+00:00"
    assert payload["level"] == "INFO"
    assert payload["component"] == "session"
    assert payload["character_count"] == 2


def test_console_debug_filtering_and_human_fields():
    output = io.StringIO()
    stream = RuntimeEventStream((ConsoleEventConsumer(stream=output),))

    stream.record("transition.started", transition="purchase_yes", attempt=1)
    stream.record("session.started", character_count=28)

    rendered = output.getvalue()
    assert "transition" not in rendered
    assert "session.started" in rendered
    assert "character_count=28" in rendered


def test_controlled_wait_emits_start_polling_and_completion_telemetry():
    fake = FakeTime()
    records = []
    stream = RuntimeEventStream((records.append,))
    wait = ControlledWait(
        check_interval=1,
        clock=fake.clock,
        sleeper=fake.sleep,
        events=stream,
        label="world_boss.completion",
    )

    result = wait.wait(
        expected_duration=3,
        completion_condition=lambda: fake.current >= 2,
    )

    assert result.succeeded
    assert [item.event for item in records] == [
        "controlled_wait.started",
        "controlled_wait.polling_started",
        "controlled_wait.completed",
    ]
    assert records[-1].fields["actual_elapsed"] == 2


def test_gui_consumer_receives_each_event_once_while_file_keeps_debug(tmp_path):
    captured = []
    path = tmp_path / "gui.log"
    stream = build_runtime_event_stream(
        path,
        debug=False,
        console=None,
        consumers=(captured.append,),
    )

    stream.record("transition.retry", transition="purchase", attempt=2)

    assert len(captured) == 1
    assert captured[0].level is EventLevel.DEBUG
    assert '"event": "transition.retry"' in path.read_text(encoding="utf-8")
