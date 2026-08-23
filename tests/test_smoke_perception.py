import os
import subprocess
import sys
from pathlib import Path

import pytest

from bot.state import ResolutionStatus, ResolvedState
from tools.smoke_perception import (
    MetricAccumulator,
    StageStability,
    should_emit_event,
    state_signature,
)


def resolved(base="screen.lobby", overlays=()):
    return ResolvedState(
        status=ResolutionStatus.RESOLVED,
        sequence=1,
        timestamp=1.0,
        base_context=base,
        overlays=overlays,
    )


def test_smoke_perception_import_is_inert(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [sys.executable, "-c", "import tools.smoke_perception"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_metric_accumulator_summarizes_session_values():
    metric = MetricAccumulator()
    for value in (0.004, 0.002, 0.010, 0.006):
        metric.add(value)

    summary = metric.summary()

    assert summary is not None
    assert summary.count == 4
    assert summary.minimum == pytest.approx(0.002)
    assert summary.median == pytest.approx(0.005)
    assert summary.mean == pytest.approx(0.0055)
    assert summary.maximum == pytest.approx(0.010)


def test_metric_accumulator_has_no_summary_without_samples():
    assert MetricAccumulator().summary() is None


def test_event_output_is_driven_by_change_or_heartbeat():
    lobby = (state_signature(resolved()), ("landmark.lobby",))
    black_market = (
        state_signature(resolved("screen.black_market")),
        ("landmark.black_market",),
    )

    assert should_emit_event(
        None, lobby, now=10.0, last_emitted_at=None, heartbeat_seconds=5.0
    )
    assert not should_emit_event(
        lobby, lobby, now=12.0, last_emitted_at=10.0, heartbeat_seconds=5.0
    )
    assert should_emit_event(
        lobby, lobby, now=15.0, last_emitted_at=10.0, heartbeat_seconds=5.0
    )
    assert should_emit_event(
        lobby, black_market, now=12.0, last_emitted_at=10.0, heartbeat_seconds=5.0
    )


def test_stage_stability_exposes_consecutive_flicker():
    tracker = StageStability()
    lobby = state_signature(resolved())
    unknown = (
        ResolutionStatus.UNKNOWN.value,
        None,
        (),
        (),
    )

    assert tracker.record(lobby) == 1
    assert tracker.record(lobby) == 2
    assert tracker.record(unknown) == 1
    assert tracker.record(lobby) == 1
    assert tracker.record(lobby) == 2

    assert tracker.analyses == 5
    assert tracker.longest_consecutive == 2
    assert tracker.dominant_signature == lobby
