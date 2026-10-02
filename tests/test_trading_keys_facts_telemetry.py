"""Keys-only diagnostics describe existing reads; they never authorize input."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.event_context import event_scope
from bot.event_log import RuntimeEventStream
from bot.flow_contracts import FlowStatus
from bot.flow_registry import _build_productive_monster_wave
from bot.keys_promotion_runtime import FreshKeyFacts, KeysPromotionRuntime
from bot.monster_wave_flow import MonsterWaveFlow
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.ocr import OcrResult
from bot.perception import build_default_perception
from bot.runtime_observer import (
    RuntimeFacts, RuntimeObserver, RuntimeSnapshot, RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_key_facts_reader import read_fresh_key_facts
from bot.trading_row_facts import TradingRowReader
from bot.verified_transition import VerifiedTransition


def snapshot(sequence):
    image = np.zeros((200, 440, 3), dtype=np.uint8)
    frame = FrameSnapshot(image, float(sequence), sequence)
    observations = ObservationBatch(sequence, float(sequence), tuple(
        Observation(name, 1.0, ObservationSource.LOCAL_CV) for name in (
            "landmark.trading_center_title", "indicator.trading_keys_active",
            "indicator.trading_keys_rows",
        )
    ))
    state = ResolvedState(ResolutionStatus.RESOLVED, sequence, float(sequence),
                          base_context="screen.trading")
    return RuntimeSnapshot(frame, observations, state, RuntimeFacts(),
                           FrameGeometry.from_frame(image))


class Observer:
    def __init__(self, sequences):
        self.snapshots = iter(snapshot(seq) for seq in sequences)
        self.waits = []

    def wait_until(self, predicate, *, after_sequence, timeout, **kwargs):
        self.waits.append((after_sequence, timeout))
        item = next(self.snapshots)
        assert predicate(item) and item.sequence > after_sequence
        return item


class Ocr:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def recognize(self, image):
        self.calls.append(image.shape)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def ocr_script(frames, *, method="localized", rows=("silver_key", "gold_key")):
    """Script title and pair output, leaving production parsing untouched."""
    titles = {"silver_key": "Silver Key 2", "gold_key": "Gold Key 2"}
    results = []
    for values in frames:
        for row in rows:
            value = values.get(row)
            title = titles[row] if value is not None else "Unrecognized"
            for expected in ("silver_key", "gold_key"):
                results.extend((OcrResult(title, .95), OcrResult("", .9)))
                if expected != row or value is None:
                    continue
                pair_reads = (value if isinstance(value, list) else
                              [OcrResult(f"{value}/10", .97)] * 2)
                results.extend(pair_reads)
    return results


def acquire(monkeypatch, frames, *, method="localized", events=True,
            rows=("silver_key", "gold_key"), reader_error=None):
    import bot.trading_key_facts_reader as acquisition
    import bot.trading_row_facts as reading

    # Keep legacy row-parser/fallback diagnostic coverage using an injected
    # sample provider; production Keys geometry is tested on native corpus
    # in test_trading_key_row_reader.py.
    def read_samples(reader, image, sequence, candidates):
        current = {}
        for index, _row in enumerate(rows):
            top, center = .36 + index * .14, .43 + index * .14
            for key in candidates:
                candidate = dict(item_id=key, row_top=top, row_y=center, ocr_calls=0)
                candidates[key].append(candidate)
                sample = reader.read_sample(image, sequence, item_id=key, section="keys",
                                            row_top=top, row_y=center, diagnostics=candidate)
                candidate["sample"] = vars(sample).copy() if sample is not None else None
                candidate["ocr_calls"] = len(candidate.get("title_reads", ())) + len(candidate.get("pair_reads", ()))
                if sample is not None:
                    current[key] = sample
        return current
    monkeypatch.setattr(acquisition, "read_key_samples", read_samples)
    monkeypatch.setattr(reading, "_localize_pair", lambda _frame, top:
                        (.495, top + .055, .55, top + .11)
                        if method == "localized" else None)
    outputs = ocr_script(frames, method=method, rows=rows)
    if reader_error is not None:
        outputs[0] = reader_error
    engine = Ocr(outputs)
    observer = Observer(range(1, len(frames) + 1))
    recorded = []
    sink = RuntimeEventStream((recorded.append,)) if events is True else events
    result = read_fresh_key_facts(
        observer, TradingRowReader(engine), after_sequence=0,
        cancel_requested=lambda: False, max_samples=len(frames), events=sink,
    )
    return result, [item.payload() for item in recorded], engine.calls, observer.waits


def event(log, suffix):
    return next(item for item in log if item["event"] == f"trading.keys.facts.{suffix}")


def identified(sample, item):
    return next(candidate for candidate in sample["candidates"][item]
                if candidate.get("identity_match"))


def test_complete_samples_consensus_and_fresh_facts(monkeypatch):
    with event_scope(run_id="run", flow="monster_wave", operation_id="mw-op",
                     session_id="session", step="monster_wave"):
        fresh, log, _, waits = acquire(monkeypatch, [
            {"silver_key": 411, "gold_key": 131},
            {"silver_key": 411, "gold_key": 131},
        ])
    assert isinstance(fresh, FreshKeyFacts)
    assert fresh.snapshot.sequence == fresh.silver_fact.sequence == fresh.gold_fact.sequence == 2
    assert waits == [(0, 6.0), (1, 6.0)]
    samples = [item for item in log if item["event"].endswith(".sample")]
    assert [item["status"] for item in samples] == ["complete", "complete"]
    assert samples[0]["source_sequence"] == samples[0]["capture_monotonic"] == 1
    assert samples[0]["is_keys_ready"] is True
    assert (samples[0]["frame_width"], samples[0]["frame_height"]) == (440, 200)
    assert samples[0]["identified_rows"] == ["silver_key", "gold_key"]
    for key, have in (("silver_key", 411), ("gold_key", 131)):
        candidate = identified(samples[0], key)
        assert candidate["pair_method"] == "localized"
        assert candidate["pair_reads"][0]["raw"] == f"{have}/10"
        assert candidate["pair_reads"][0]["confidence"] == .97
        assert candidate["parse_result"] == (have, 10)
        assert candidate["sample"]["have"] == have
        assert candidate["title_reads"][0]["confidence"] == .95
        comparison = event(log, "consensus")["comparisons"][key]
        assert comparison["source_sequences"] == [1, 2]
        assert comparison["values"] == [[have, 10], [have, 10]]
        assert comparison["identity_match"] and comparison["balances_match"]
        assert comparison["position_delta"] == 0
        assert comparison["position_tolerance"] == .01
        assert comparison["position_tolerance_result"] and comparison["accepted"]
        assert comparison["fact"]["sequence"] == 2
    ready = event(log, "ready")
    assert ready["source_sequences"] == [1, 2]
    assert (ready["silver_have"], ready["silver_need"], ready["gold_have"], ready["gold_need"]) == (411, 10, 131, 10)
    assert len({item["acquisition_id"] for item in log}) == 1
    assert all(item["operation_id"] == "mw-op" and item["run_id"] == "run" for item in log)
    json.dumps(log)  # No image objects, arrays or base64 in the payload.


@pytest.mark.parametrize("missing", ("silver_key", "gold_key"))
def test_missing_row_has_correct_code_and_summary(monkeypatch, missing):
    frames = [{"silver_key": 40, "gold_key": 20} for _ in range(4)]
    for frame in frames:
        del frame[missing]
    fresh, log, _, waits = acquire(monkeypatch, frames)
    assert fresh is None and len(waits) == 4
    assert event(log, "sample")["status"] == "incomplete"
    assert event(log, "sample")["reason"] == f"missing_{missing}"
    failed = event(log, "unavailable")
    assert failed["samples_attempted"] == 4
    assert failed["reason"] == "samples_exhausted"
    assert failed["source_sequences"] == [1, 2, 3, 4]
    assert all(item["missing_rows"] == [missing] for item in failed["sample_summary"])
    assert not any(item["event"].endswith((".ready", ".consensus")) for item in log)


@pytest.mark.parametrize("raw,confidence,reason", (
    ("411", .97, "parse_failed"),
    ("411/10", .49, "ocr_low_confidence"),
))
def test_rejected_ocr_has_raw_confidence_and_parser_reason(monkeypatch, raw, confidence, reason):
    # A failed first parse short-circuits the second crop in both methods.
    value = [OcrResult(raw, confidence), OcrResult(raw, confidence)]
    fresh, log, _, _ = acquire(monkeypatch, [{"silver_key": value, "gold_key": 20}])
    assert fresh is None
    candidate = identified(event(log, "sample"), "silver_key")
    assert candidate["reason"] == candidate["localized_reason"] == candidate["fallback_reason"] == reason
    assert [read["method"] for read in candidate["pair_reads"]] == ["localized", "fallback"]
    assert all(read["raw"] == raw and read["confidence"] == confidence
               and read["parse_result"] is None and read["reason"] == reason
               for read in candidate["pair_reads"])


def test_fallback_used_without_extra_ocr_calls(monkeypatch):
    frames = [{"silver_key": 40, "gold_key": 20}] * 2
    fresh, log, calls, waits = acquire(monkeypatch, frames, method="fallback")
    plain, _, plain_calls, plain_waits = acquire(monkeypatch, frames, method="fallback", events=None)
    assert fresh.silver_fact == plain.silver_fact and fresh.gold_fact == plain.gold_fact
    assert fresh.snapshot.sequence == plain.snapshot.sequence
    assert calls == plain_calls and waits == plain_waits
    candidate = identified(event(log, "sample"), "silver_key")
    assert candidate["pair_method"] == "fallback"
    assert candidate["localized_reason"] == "pair_not_localized"
    assert candidate["fallback_reason"] is None
    assert len(candidate["fallback_rois"]) == len(candidate["pair_reads"]) == 2
    assert all(item["method"] == "fallback" for item in candidate["pair_reads"])


def test_fallback_disagreement_is_distinct_from_parse_failure(monkeypatch):
    values = [OcrResult("40/10", .95), OcrResult("41/10", .95)]
    fresh, log, _, _ = acquire(monkeypatch, [{"silver_key": values, "gold_key": 20}], method="fallback")
    assert fresh is None
    candidate = identified(event(log, "sample"), "silver_key")
    assert candidate["reason"] == "fallback_disagrees"
    assert [read["parse_result"] for read in candidate["pair_reads"]] == [(40, 10), (41, 10)]
    assert all(read["reason"] is None for read in candidate["pair_reads"])


def test_localized_disagreement_then_fallback_success(monkeypatch):
    values = [OcrResult(f"{have}/10", .95) for have in (40, 41, 40, 40)]
    fresh, log, _, _ = acquire(monkeypatch, [{"silver_key": values, "gold_key": 20}] * 2)
    assert isinstance(fresh, FreshKeyFacts)
    candidate = identified(event(log, "sample"), "silver_key")
    assert candidate["localized_reason"] == "localized_disagrees"
    assert candidate["pair_method"] == "fallback" and candidate["reason"] is None


def test_valid_discordant_samples_are_consensus_failure(monkeypatch):
    fresh, log, _, _ = acquire(monkeypatch, [
        {"silver_key": 40 + seq % 2, "gold_key": 20} for seq in range(4)
    ])
    assert fresh is None
    assert all(item["status"] == "complete" for item in log if item["event"].endswith(".sample"))
    comparison = event(log, "consensus")["comparisons"]
    assert comparison["silver_key"]["reasons"] == ["balances_mismatch"]
    assert not comparison["silver_key"]["balances_match"]
    assert comparison["silver_key"]["identity_match"] and comparison["silver_key"]["position_tolerance_result"]
    assert comparison["gold_key"]["accepted"]
    assert event(log, "unavailable")["sample_summary"][-1]["consensus"]["silver_key"]["reasons"] == ["balances_mismatch"]


@pytest.mark.parametrize("change,reason", (
    ({"row_y": .48}, "position_mismatch"),
    ({"item_id": "gold_key"}, "identity_mismatch"),
    ({"sequence": 1}, "stale_sequence"),
))
def test_consensus_trace_matches_existing_guards(monkeypatch, change, reason):
    from dataclasses import replace
    original = TradingRowReader.read_sample

    def read(reader, frame, sequence, **kwargs):
        sample = original(reader, frame, sequence, **kwargs)
        if sample is not None and sequence == 2 and sample.item_id == "silver_key":
            return replace(sample, **change)
        return sample

    monkeypatch.setattr(TradingRowReader, "read_sample", read)
    fresh, log, _, _ = acquire(monkeypatch, [{"silver_key": 40, "gold_key": 20}] * 2)
    assert fresh is None
    comparison = event(log, "consensus")["comparisons"]["silver_key"]
    assert comparison["reasons"] == [reason]
    assert comparison["accepted"] is False
    if reason == "position_mismatch":
        assert comparison["position_delta"] == pytest.approx(.05)
        assert comparison["position_tolerance_result"] is False


@pytest.mark.parametrize("frames,method", (
    ([{"silver_key": 40, "gold_key": 20}] * 2, "localized"),
    ([{"gold_key": 20}] * 4, "localized"),
    ([{"silver_key": 40 + seq % 2, "gold_key": 20} for seq in range(4)], "localized"),
    ([{"silver_key": [OcrResult("40", .97)] * 2, "gold_key": 20}], "localized"),
    ([{"silver_key": [OcrResult("40/10", .95), OcrResult("41/10", .95)], "gold_key": 20}], "fallback"),
))
def test_logging_preserves_success_rejection_and_ocr_call_order(monkeypatch, frames, method):
    fresh, _, calls, waits = acquire(monkeypatch, frames, method=method)
    plain, _, plain_calls, plain_waits = acquire(monkeypatch, frames, method=method, events=None)
    assert (fresh is None) == (plain is None)
    if fresh is not None:
        assert fresh.silver_fact == plain.silver_fact and fresh.gold_fact == plain.gold_fact
        assert fresh.snapshot.sequence == plain.snapshot.sequence
    assert calls == plain_calls and waits == plain_waits


def test_mixed_rejections_preserve_all_four_samples(monkeypatch):
    fresh, log, _, _ = acquire(monkeypatch, [
        {"gold_key": 20}, {"silver_key": 40}, {}, {"silver_key": 40, "gold_key": 20},
    ])
    assert fresh is None
    assert [item["reason"] for item in event(log, "unavailable")["sample_summary"]] == [
        "missing_silver_key", "missing_gold_key", "sample_incomplete", None,
    ]


def test_geometry_provider_never_scans_or_duplicates_output_identities():
    from bot.trading_key_row_reader import read_key_samples
    # A frame lacking the two title anchors yields no candidate facts;
    # the former cross-product scan of every title has been removed.
    reader = TradingRowReader(Ocr([]))
    candidates = {"silver_key": [], "gold_key": []}
    assert read_key_samples(reader, snapshot(1).frame.image, 1, candidates) == {}
    assert all(len(values) == 1 for values in candidates.values())
    assert all(values[0]["identity_match"] is False for values in candidates.values())
    assert not reader.engine.calls


def test_sink_failure_does_not_change_reads_or_return(monkeypatch):
    frames = [{"silver_key": 40, "gold_key": 20}] * 2
    failed_sink = Mock()
    failed_sink.record.side_effect = RuntimeError("sink unavailable")
    fresh, _, calls, waits = acquire(monkeypatch, frames, events=failed_sink)
    plain, _, plain_calls, plain_waits = acquire(monkeypatch, frames, events=None)
    assert fresh.silver_fact == plain.silver_fact and fresh.gold_fact == plain.gold_fact
    assert fresh.snapshot.sequence == plain.snapshot.sequence
    assert calls == plain_calls and waits == plain_waits


def test_reader_exception_is_logged_and_same_exception_propagates(monkeypatch):
    import bot.trading_key_facts_reader as acquisition
    error = RuntimeError("OCR backend failed")
    sink = Mock()
    reader = TradingRowReader(Ocr([error]))
    def fail_read(reader, frame, sequence, candidates):
        raise error
    monkeypatch.setattr(acquisition, "read_key_samples", fail_read)
    with pytest.raises(RuntimeError) as raised:
        read_fresh_key_facts(Observer([1]), reader, after_sequence=0,
                             cancel_requested=lambda: False, events=sink)
    assert raised.value is error
    terminal = sink.record.call_args
    assert terminal.args == ("trading.keys.facts.unavailable",)
    assert terminal.kwargs["exception_type"] == "RuntimeError"
    assert terminal.kwargs["reason"] == "read_exception"
    assert terminal.kwargs["sample_summary"][0]["status"] == "rejected"


@pytest.mark.parametrize("error,reason", (
    (RuntimeWaitCancelled("cancelled"), "cancelled"),
    (RuntimeWaitTimeout(after_sequence=0, timeout=6, last_snapshot=None), "read_exception"),
))
def test_wait_exception_is_not_swallowed(error, reason):
    observer = Mock()
    observer.wait_until.side_effect = error
    sink = Mock()
    with pytest.raises(type(error)) as raised:
        read_fresh_key_facts(observer, Mock(), after_sequence=0,
                             cancel_requested=lambda: False, events=sink)
    assert raised.value is error
    assert sink.record.call_args.kwargs["reason"] == reason
    assert sink.record.call_args.kwargs["source_sequences"] == []


def test_logging_never_authorizes_trade_and_failure_keeps_op_correlation(monkeypatch):
    import bot.trading_key_facts_reader as acquisition
    monkeypatch.setattr(acquisition, "read_key_samples", lambda *args: {})
    reader = TradingRowReader(Ocr([OcrResult("Unrecognized", .95)] * 16))
    observer = Observer([1, 2, 3, 4])
    recorded = []
    sink = RuntimeEventStream((recorded.append,))
    trading = Mock()
    trading.ensure_avatar_keys.return_value = SimpleNamespace(
        status=FlowStatus.COMPLETED, final_snapshot=snapshot(0),
    )
    trade = Mock(side_effect=AssertionError("must not trade"))
    runtime = KeysPromotionRuntime(
        trading, Mock(), Mock(),
        read_key_facts=lambda barrier: read_fresh_key_facts(
            observer, reader, after_sequence=barrier,
            cancel_requested=lambda: False, events=sink,
        ), execute_key_trade=trade, drain_gold_keys=Mock(),
    )
    with event_scope(flow="monster_wave", operation_id="mw-op"):
        result = runtime.run()
        sink.record("flow.failed", error=result.error)
    assert result.status is FlowStatus.FAILED and result.error == "fresh_key_facts_unavailable"
    assert not result.trade_attempts and result.decision is None and result.remaining_budget is None
    trade.assert_not_called()
    trading.leave_to_lobby.assert_not_called()
    assert recorded[-1].fields["operation_id"] == recorded[-2].fields["operation_id"] == "mw-op"
    assert recorded[-2].event == "trading.keys.facts.unavailable"


def test_productive_builder_forwards_existing_sink(monkeypatch):
    from pathlib import Path
    import bot.trading_key_facts_reader as acquisition
    from bot.ocr import RapidOcrEngine

    monkeypatch.setattr(RapidOcrEngine, "recognize", lambda *_: OcrResult("", 0))
    callback = Mock(return_value=None)
    monkeypatch.setattr(acquisition, "read_fresh_key_facts", callback)
    root = Path(__file__).resolve().parents[1]
    source = Mock()
    source.get_frame.side_effect = AssertionError("must not capture")
    adb = Mock()
    adb.tap.side_effect = AssertionError("must not tap")
    observer = RuntimeObserver(source, build_default_perception(root), build_default_resolver())
    actions = ActionExecutor(adb)
    sink = RuntimeEventStream()
    inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
    inner.activity = SimpleNamespace()
    inner.zone = object()
    dependencies = SimpleNamespace(
        observer=observer, actions=actions, events=sink,
        cancel_requested=lambda: False,
        equipment_combine_relief=SimpleNamespace(run=lambda *_args: None), socket_relief=None,
    )
    flow = _build_productive_monster_wave(dependencies, VerifiedTransition(observer, actions, sink), lambda: inner)
    assert flow.route.keys_runtime.read_key_facts(3323) is None
    assert callback.call_args.kwargs["events"] is sink
    assert callback.call_args.kwargs["after_sequence"] == 3323
    source.get_frame.assert_not_called()
    adb.tap.assert_not_called()
