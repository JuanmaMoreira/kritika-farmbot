"""Terminal evidence, real observer/runners and storage faults without hardware."""

from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import cv2
import numpy as np
import pytest

import bot.failure_evidence as evidence_module
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY, LANDMARK_LOBBY_TRADING_CENTER_LABEL, build_default_resolver
from bot.daily_quests_flow import DailyQuestsFlow
from bot.event_context import event_scope, operation_scope
from bot.event_log import JsonLineEventConsumer, RuntimeEventStream
from bot.failure_cause import FailureCause
from bot.failure_evidence import FailureEvidence, json_bytes, publish_failure, snapshot_payload
from bot.flow_contracts import FlowResult, FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.rotation import RotationOutcome, RotationResult
from bot.runtime_observer import RuntimeObserver, RuntimeWaitTimeout
from bot.session import SessionStatus
from test_daily_quests_flow import Actions, snapshot
from test_productive_runtime import _runtime
from test_runtime_observer import Clock, Perception, Source
from test_session import Flow, Rotation, _runner


def fail(*args, **kwargs):
    raise OSError("injected diagnostic fault")


def bundle_path(reference):
    value = unquote(urlparse(reference).path)
    if os.name == "nt":
        value = value.lstrip("/")
    return Path(value)


def setup_stream(tmp_path):
    evidence = FailureEvidence(tmp_path / "evidence")
    records = []
    stream = RuntimeEventStream((JsonLineEventConsumer(tmp_path / "events.jsonl"), records.append),
                                run_id="run-test", failure_evidence=evidence)
    return evidence, stream, records


@pytest.mark.parametrize("count", [0, 1, 2, 3, 6])
def test_bounded_ordered_correlated_bundle_and_canonical_event(tmp_path, count):
    evidence, stream, records = setup_stream(tmp_path)
    with event_scope(session_id="session-test", character_index=2, flow="daily_quests"), operation_scope("claim"):
        for i in range(1, count + 1):
            current = snapshot(i, float(i), base=SCREEN_LOBBY)
            current.frame.image[:] = i
            evidence.observe(current)
            current.frame.image[:] = 255  # The ring owns its image.
            evidence.observe(current)  # Repeated sequences don't evict fresh samples.
        cause = FailureCause.from_error("state_wait_failed", sequence=count)
        linked = publish_failure(stream, "flow.failed", cause)
        publish_failure(stream, "session.failed", linked)
    assert linked is not cause and replace(linked, evidence_ref=None) == cause
    path = bundle_path(linked.evidence_ref)
    data = json.loads(path.read_text())
    assert data["failure"] == linked.payload()
    assert data["event"]["run_id"] == "run-test"
    assert data["event"]["session_id"] == "session-test"
    assert data["event"]["character_index"] == 2
    assert data["event"]["event_sequence"] == records[0].fields["event_sequence"]
    expected = list(range(max(1, count - 2), count + 1))
    assert [s["sequence"] for s in data["snapshots"]] == expected
    for item in data["snapshots"]:
        metadata = json.loads((path.parent / item["snapshot"]).read_text())
        frame = cv2.imread(str(path.parent / item["frame"]))
        assert np.all(frame == item["sequence"])
        assert metadata["sequence"] == metadata["state"]["sequence"] == item["sequence"]
        assert metadata["frame"]["file"] == item["frame"]
        assert metadata["context"]["flow"] == "daily_quests"
    payloads = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert all(p["failure"]["evidence_ref"] == linked.evidence_ref for p in payloads)
    assert len(list(evidence.root.iterdir())) == 1


@pytest.mark.parametrize("event,kind,exception", [
    ("runtime_wait.completed", "timeout", "RuntimeWaitTimeout"),
    ("transition.completed", "timeout", None),
    ("auto_battle.timeout", "timeout", None),
    ("flow.completed", "timeout", None),
    ("flow.cancelled", "cancelled", None),
    ("session.cancelled", "cancelled", None),
    ("runtime.failed", "exception", "KeyboardInterrupt"),
    ("flow.failed", "exception", "RuntimeWaitCancelled"),
    ("rotation.failed", "cancelled", None),
])
def test_nonterminal_and_cancellation_never_write(tmp_path, event, kind, exception):
    evidence, stream, _ = setup_stream(tmp_path)
    original = FailureCause(kind, "failure", exception_type=exception)
    assert publish_failure(stream, event, original) is original
    assert not evidence.root.exists()


@pytest.mark.parametrize("stage", ["mkdir", "encode", "encode_false", "serialize", "write"])
def test_writer_fault_preserves_failure_and_event_without_recursion(tmp_path, monkeypatch, stage):
    evidence, stream, records = setup_stream(tmp_path)
    evidence.observe(snapshot(1, 1.0, base=SCREEN_LOBBY))
    if stage == "mkdir":
        monkeypatch.setattr(Path, "mkdir", fail)
    elif stage == "encode":
        monkeypatch.setattr(cv2, "imencode", fail)
    elif stage == "encode_false":
        monkeypatch.setattr(cv2, "imencode", lambda *a: (False, None))
    elif stage == "serialize":
        monkeypatch.setattr(evidence_module, "json_bytes", fail)
    else:
        original_open = Path.open
        def failed_write(path, *args, **kwargs):
            if path.name.startswith("snapshot_"):
                raise OSError("disk full")
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", failed_write)
    cause = FailureCause("timeout", "original", sequence=1)
    assert publish_failure(stream, "flow.failed", cause) is cause
    assert len(records) == 1 and records[0].fields["failure"] == cause.payload()
    assert not list(evidence.root.glob("failure_*"))


def test_strict_projection_preserves_semantics_and_omits_unsafe_objects(tmp_path):
    current = snapshot(4, 5.0, base=None, overlays=("menu.quick",))
    observation = Observation("slot.gold", 0.9, ObservationSource.LOCAL_CV, value=3,
                              region=(0.1, 0.2, 0.3, 0.4))
    current = replace(current, observations=ObservationBatch(4, 5.0, (observation,)))
    first = json_bytes(snapshot_payload(current))
    assert first == json_bytes(snapshot_payload(current))
    data = json.loads(first)
    assert data["state"]["status"] == "unknown"
    assert data["state"]["overlays"] == ["menu.quick"]
    assert data["observations"][0]["source"] == "local_cv"
    assert "image" not in data and "frame" not in data
    with pytest.raises(TypeError):
        json_bytes({"unsafe": object()})
    with pytest.raises(ValueError):
        json_bytes({"nonfinite": float("nan")})


def test_downscale_memory_bound_and_cleanup(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    image = np.zeros((1400, 2800, 3), np.uint8)
    for i in range(1, 7):
        original = snapshot(i, float(i), base=SCREEN_LOBBY)
        evidence.observe(replace(original, frame=FrameSnapshot(image, float(i), i),
                                 geometry=FrameGeometry.from_frame(image)))
    assert evidence.retained_bytes < 3 * (960 * 480 * 3 + 4096)
    linked = publish_failure(stream, "flow.failed", FailureCause("failed", "original"))
    path = bundle_path(linked.evidence_ref)
    for frame in path.parent.glob("*.png"):
        assert cv2.imread(str(frame)).shape == (480, 960, 3)
    evidence.close()
    assert evidence.retained_bytes == 0
    evidence.observe(original)
    assert evidence.retained_bytes == 0


def test_metadata_only_sample_is_valid_when_image_unavailable(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    current = snapshot(1, 1.0, base=SCREEN_LOBBY)
    evidence.observe(SimpleNamespace(**{**vars(current), "frame": SimpleNamespace(image=None),
                                       "sequence": 1, "timestamp": 1.0}))
    linked = publish_failure(stream, "flow.failed", FailureCause("failed", "original"))
    data = json.loads(bundle_path(linked.evidence_ref).read_text())
    assert data["snapshots"] == [{"sequence": 1, "snapshot": "snapshot_1.json", "frame": None}]


def test_real_observer_handled_wait_and_bad_callback_preserve_behavior(tmp_path):
    evidence, stream, records = setup_stream(tmp_path)
    clock = Clock()
    observer = RuntimeObserver(Source([1, 2, 3]), Perception(), build_default_resolver(),
                               clock=clock, sleeper=clock.sleep, events=stream,
                               snapshot_consumer=evidence.observe)
    with pytest.raises(RuntimeWaitTimeout):
        observer.wait_until(lambda s: False, after_sequence=0, timeout=0.1)
    assert not evidence.root.exists()
    assert records[-1].fields["failure"]["evidence_ref"] is None
    observer._snapshot_consumer = fail
    assert observer.observe().sequence == 3


@pytest.mark.parametrize("terminal", ["flow", "rotation", "precondition", "postcondition", "cancel"])
def test_session_propagates_one_bundle_and_keeps_original_execution_trace(tmp_path, terminal):
    traces = []
    for enabled in (False, True):
        trace = []
        result = FlowResult(FlowStatus.FAILED, error="state_wait_failed") if terminal == "flow" else FlowResult(FlowStatus.COMPLETED)
        flow = Flow("daily_quests", [result], trace)
        rotation = Rotation(1, trace, [RotationResult(RotationOutcome.ABORTED, error="sentinel_not_found")]
                            if terminal == "rotation" else None)
        kwargs = {"default_context": None} if terminal == "precondition" else {}
        if terminal == "postcondition":
            kwargs["context_values"] = [SCREEN_LOBBY, None]
        runner, _ = _runner(1, [flow], rotation, trace=trace,
                             cancel_requested=lambda: terminal == "cancel", **kwargs)
        evidence, stream, records = setup_stream(tmp_path / str(enabled))
        runner.events = stream
        if not enabled:
            stream.failure_evidence = None
        session = runner.run()
        traces.append(trace)
        if enabled and terminal != "cancel":
            assert session.status == SessionStatus.FAILED
            assert session.failure.evidence_ref
            assert len(list(evidence.root.iterdir())) == 1
            failed = [r for r in records if r.event.endswith(".failed")]
            assert all(r.fields["failure"]["evidence_ref"] == session.failure.evidence_ref for r in failed)
            if terminal == "flow":
                assert session.character_results[0].flow_results[0].failure == session.failure
            if terminal == "rotation":
                assert session.character_results[0].advance_result.failure == session.failure
        else:
            assert not evidence.root.exists()
    assert traces[0] == traces[1]


def test_actual_daily_terminal_timeout_inputs_identical_with_evidence(tmp_path):
    traces = []
    for enabled in (False, True, "failed_writer"):
        evidence, stream, _ = setup_stream(tmp_path / str(enabled))
        if not enabled:
            stream.failure_evidence = None
        elif enabled == "failed_writer":
            evidence._write = fail
        clock = Clock()
        perception = Perception((Observation(LANDMARK_LOBBY_TRADING_CENTER_LABEL, 1.0, ObservationSource.SYSTEM),))
        observer = RuntimeObserver(Source(list(range(1, 100))), perception, build_default_resolver(),
                                   clock=clock, sleeper=clock.sleep, events=stream,
                                   snapshot_consumer=evidence.observe if enabled else None)
        actions = Actions()
        flow = DailyQuestsFlow(observer, actions, stream, navigation_timeout=0.1,
                               clock=clock, sleeper=clock.sleep)
        runner, _ = _runner(1, [flow], Rotation(1, []))
        runner.events = stream
        result = runner.run()
        assert result.status == SessionStatus.FAILED
        assert "state_wait_failed" in result.failure.message
        assert bool(result.failure.evidence_ref) == (enabled is True)
        traces.append(actions.items)
    assert traces[0] == traces[1] == traces[2] and len(traces[0]) == 1


def test_standalone_result_and_exception_propagation(tmp_path):
    evidence, stream, records = setup_stream(tmp_path)
    runtime = _runtime(object(), stream)
    flow = Flow("daily_quests", [FlowResult(FlowStatus.FAILED, error="failure")], [])
    runtime.build_flow = lambda _: flow
    runtime.build_preconditions = lambda: SimpleNamespace(ensure=lambda _: SimpleNamespace(succeeded=True))
    definition = SimpleNamespace(id="daily_quests")
    result = runtime.run_flow(definition)
    assert result.failure.evidence_ref == records[-1].fields["failure"]["evidence_ref"]
    flow.run = lambda: fail()
    with pytest.raises(OSError) as caught:
        runtime.run_flow(definition)
    cause = caught.value.failure
    publish_failure(stream, "runtime.failed", cause)
    assert len(list(evidence.root.iterdir())) == 2


def test_retention_count_age_and_foreign_evidence_protection(tmp_path, monkeypatch):
    evidence, stream, _ = setup_stream(tmp_path)
    monkeypatch.setattr(evidence_module, "MAX_BUNDLES", 2)
    refs = [publish_failure(stream, "flow.failed", FailureCause("failed", "same")).evidence_ref for _ in range(4)]
    assert len(set(refs)) == 4
    assert len(list(evidence.root.iterdir())) == 2
    foreign = evidence.root / ("failure_" + "a" * 32)
    foreign.mkdir()
    (foreign / ".owner").write_bytes(evidence_module._OWNER)
    (foreign / "curated.txt").write_text("valuable")
    for path in evidence.root.iterdir():
        os.utime(path, (0, 0))
    evidence._prune()
    assert list(evidence.root.iterdir()) == [foreign]
    assert (foreign / "curated.txt").read_text() == "valuable"


def test_retention_bytes_and_bundle_limit(tmp_path, monkeypatch):
    evidence, stream, _ = setup_stream(tmp_path)
    first = publish_failure(stream, "flow.failed", FailureCause("failed", "first"))
    size = sum(p.stat().st_size for p in bundle_path(first.evidence_ref).parent.iterdir())
    monkeypatch.setattr(evidence_module, "MAX_STORAGE_BYTES", size * 2 - 1)
    publish_failure(stream, "flow.failed", FailureCause("failed", "other"))
    assert len(list(evidence.root.iterdir())) == 1
    monkeypatch.setattr(evidence_module, "MAX_BUNDLE_BYTES", 1)
    original = FailureCause("failed", "too large")
    assert publish_failure(stream, "flow.failed", original) is original


def test_name_collision_does_not_overwrite_existing_bundle(tmp_path, monkeypatch):
    evidence, stream, _ = setup_stream(tmp_path)
    monkeypatch.setattr(evidence_module, "uuid4", lambda: SimpleNamespace(hex="b" * 32))
    first = publish_failure(stream, "flow.failed", FailureCause("failed", "first"))
    path = bundle_path(first.evidence_ref)
    content = path.read_bytes()
    second = FailureCause("failed", "second")
    assert publish_failure(stream, "flow.failed", second) is second
    assert path.read_bytes() == content


def test_prune_error_keeps_original_failure_and_existing_evidence(tmp_path, monkeypatch):
    evidence, stream, _ = setup_stream(tmp_path)
    first = publish_failure(stream, "flow.failed", FailureCause("failed", "first"))
    monkeypatch.setattr(evidence_module, "MAX_BUNDLES", 1)
    monkeypatch.setattr(Path, "unlink", fail)
    second = FailureCause("failed", "second")
    assert publish_failure(stream, "flow.failed", second) is second
    assert bundle_path(first.evidence_ref).exists()


def test_regressing_sequences_and_failed_samples_cannot_evict_valid_window(tmp_path, monkeypatch):
    evidence, stream, _ = setup_stream(tmp_path)
    for i in (5, 6, 7, 2, 6):
        evidence.observe(snapshot(i, float(i), base=SCREEN_LOBBY))
    with monkeypatch.context() as patch:
        patch.setattr(evidence_module, "snapshot_payload", fail)
        evidence.observe(snapshot(8, 8.0, base=SCREEN_LOBBY))
    linked = publish_failure(stream, "flow.failed", FailureCause("failed", "failure"))
    data = json.loads(bundle_path(linked.evidence_ref).read_text())
    assert [s["sequence"] for s in data["snapshots"]] == [5, 6, 7]


def test_enricher_error_does_not_block_canonical_consumers(tmp_path):
    _, stream, records = setup_stream(tmp_path)
    stream.failure_evidence = SimpleNamespace(enrich=fail)
    original = FailureCause("failed", "original")
    assert publish_failure(stream, "flow.failed", original) is original
    assert records[0].fields["failure"] == original.payload()


def test_root_resolution_error_disables_evidence_without_masking_failure(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", fail)
        evidence = FailureEvidence(tmp_path)
    stream = RuntimeEventStream(failure_evidence=evidence)
    original = FailureCause("failed", "original")
    assert publish_failure(stream, "flow.failed", original) is original


def test_terminal_result_without_optional_error_gets_legacy_metadata(tmp_path):
    _, stream, _ = setup_stream(tmp_path)
    runtime = _runtime(object(), stream)
    flow = Flow("daily_quests", [FlowResult(FlowStatus.FAILED)], [])
    runtime.build_flow = lambda _: flow
    runtime.build_preconditions = lambda: SimpleNamespace(ensure=lambda _: SimpleNamespace(succeeded=True))
    result = runtime.run_flow(SimpleNamespace(id="daily_quests"))
    assert result.error is None
    assert result.status is FlowStatus.FAILED
    assert result.failure.type == "legacy_error"
    assert result.failure.message == "flow_failed"
    assert result.failure.evidence_ref
