import json

import pytest

from tools.black_market_gold_evaluation import load_currency_manifest


def _payload(**entry_overrides):
    entry = {
        "path": "screencaps/example.png",
        "review_status": "human_confirmed",
        "slots": ["GOLD", *("KARATS" for _ in range(9))],
    }
    entry.update(entry_overrides)
    return {"version": 1, "entries": [entry]}


def test_currency_manifest_preserves_ten_row_major_labels(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    entries = load_currency_manifest(path)

    assert len(entries) == 1
    assert entries[0].path == "screencaps/example.png"
    assert entries[0].slots == ("GOLD", *("KARATS" for _ in range(9)))


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"path": "../outside.png"}, "repository-relative"),
        ({"review_status": "predicted"}, "review_status"),
        ({"slots": ["GOLD"] * 9}, "exactly ten"),
        ({"slots": ["KARATS"] * 9 + ["UNKNOWN"]}, "currency label"),
    ),
)
def test_currency_manifest_rejects_unsafe_or_unsupported_entries(
    tmp_path, overrides, message
):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_payload(**overrides)), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_currency_manifest(path)


def test_currency_manifest_rejects_duplicate_paths(tmp_path):
    payload = _payload()
    payload["entries"].append(dict(payload["entries"][0]))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_currency_manifest(path)
