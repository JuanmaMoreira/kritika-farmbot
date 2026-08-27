import json
from datetime import datetime, timezone

from bot.event_log import JsonLineEventLog


def test_json_line_event_log_persists_timestamp_event_and_structured_fields(tmp_path):
    path = tmp_path / "events.jsonl"
    event_log = JsonLineEventLog(
        path,
        now=lambda: datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc),
    )

    event_log.record(
        "black_market.low_gold",
        character_index=3,
        character_name=None,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "timestamp": "2026-08-26T12:30:00+00:00",
        "event": "black_market.low_gold",
        "character_index": 3,
        "character_name": None,
    }
