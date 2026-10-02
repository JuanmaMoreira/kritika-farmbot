"""Fresh, bounded reads of the two causal rows on Avatars & Keys."""

from __future__ import annotations

from time import monotonic, perf_counter

from bot.event_context import new_correlation_id
from bot.event_log import record_best_effort
from bot.keys_promotion_runtime import FreshKeyFacts, VerifiedKeyTradeResult
from bot.trading_key_row_reader import read_key_samples
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.trading_keys import is_keys_ready
from bot.trading_keys import execute_key_trade
from bot.trading_panel_profile import panel_targets
from bot.trading_row_facts import (
    KEYS_SECTION, TradingRowReader, consensus_row_samples,
)


def read_fresh_key_facts(observer, reader: TradingRowReader, *,
                         after_sequence: int, cancel_requested,
                         max_samples: int = 3, events=None) -> FreshKeyFacts | None:
    """Require two matching, complete, same-frame row reads after a barrier.

    Optional diagnostics use the caller's event context plus acquisition_id;
    OCR evidence comes from the existing reads, never extra captures or reads.
    """
    acquisition_started = perf_counter()
    samples = {"silver_key": [], "gold_key": []}
    barrier = int(after_sequence)
    acquisition_id = new_correlation_id()
    source_sequences = []
    summaries = []
    attempts = 0
    sample_detail = None

    def record(event, **fields):
        record_best_effort(events, event, acquisition_id=acquisition_id,
                           elapsed_seconds=perf_counter() - acquisition_started,
                           after_sequence=after_sequence, **fields)

    def record_sample(status, reason, current):
        sample_detail.update(status=status, reason=reason,
                             identified_rows=list(current),
                             missing_rows=[key for key in samples if key not in current])
        record("trading.keys.facts.sample", level="DEBUG", **sample_detail)
        summaries.append({
            "source_sequence": sample_detail["source_sequence"],
            "status": status, "reason": reason,
            "missing_rows": sample_detail["missing_rows"],
            "candidate_reasons": {
                key: [item.get("reason") for item in values]
                for key, values in sample_detail["candidates"].items()
            },
        })

    def unavailable(reason, **fields):
        record("trading.keys.facts.unavailable", reason=reason,
               samples_attempted=attempts, source_sequences=source_sequences,
               sample_summary=summaries, **fields)

    try:
        for _ in range(max_samples):
            attempts += 1
            sample_detail = None
            snapshot_started = perf_counter()
            snapshot = observer.wait_until(
                is_keys_ready, after_sequence=barrier, timeout=6.0,
                cancel_requested=cancel_requested,
            )
            if not isinstance(snapshot, RuntimeSnapshot):
                unavailable("invalid_snapshot")
                return None
            barrier = snapshot.sequence
            source_sequences.append(barrier)
            frame = snapshot.frame.image
            sample_detail = {
                "source_sequence": barrier, "capture_monotonic": snapshot.timestamp,
                "snapshot_seconds": perf_counter() - snapshot_started,
                "is_keys_ready": is_keys_ready(snapshot),
                "frame_width": int(frame.shape[1]), "frame_height": int(frame.shape[0]),
                "candidates": {key: [] for key in samples},
            }
            current = {}
            read_started = perf_counter()
            current = read_key_samples(reader, frame, snapshot.sequence,
                                       sample_detail["candidates"])
            sample_detail["reader_seconds"] = perf_counter() - read_started
            sample_detail["ocr_calls"] = sum(
                item["ocr_calls"] for values in sample_detail["candidates"].values()
                for item in values)
            if set(current) != set(samples):
                missing = [key for key in samples if key not in current]
                reason = (f"missing_{missing[0]}" if len(missing) == 1
                          else "sample_incomplete")
                record_sample("incomplete", reason, current)
                for values in samples.values():
                    values.clear()
                continue
            record_sample("complete", None, current)
            for item_id, sample in current.items():
                samples[item_id].append(sample)
            # Title-anchored geometry stays stable; reject a physical shift.
            consensus_started = perf_counter()
            silver = consensus_row_samples(
                samples["silver_key"][-2:], row_tolerance=0.01,
            )
            gold = consensus_row_samples(
                samples["gold_key"][-2:], row_tolerance=0.01,
            )
            if len(samples["silver_key"]) >= 2:
                comparisons = {}
                for key, fact in (("silver_key", silver), ("gold_key", gold)):
                    first, second = samples[key][-2:]
                    identity_match = (first.item_id == second.item_id
                                      and first.section == second.section)
                    balances_match = (first.have == second.have and first.need == second.need)
                    delta = abs(first.row_y - second.row_y)
                    reasons = []
                    if not identity_match:
                        reasons.append("identity_mismatch")
                    if not balances_match:
                        reasons.append("balances_mismatch")
                    if delta > 0.01:
                        reasons.append("position_mismatch")
                    if second.sequence <= first.sequence:
                        reasons.append("stale_sequence")
                    comparisons[key] = dict(
                        source_sequences=[first.sequence, second.sequence],
                        values=[[first.have, first.need], [second.have, second.need]],
                        row_positions=[first.row_y, second.row_y], position_delta=delta,
                        identity_match=identity_match, balances_match=balances_match,
                        position_tolerance=0.01, position_tolerance_result=delta <= 0.01,
                        sequence_increasing=second.sequence > first.sequence,
                        accepted=fact is not None, reasons=reasons,
                        fact=vars(fact).copy() if fact is not None else None,
                    )
                record("trading.keys.facts.consensus", source_sequence=barrier,
                       consensus_seconds=perf_counter() - consensus_started,
                       comparisons=comparisons, accepted=silver is not None and gold is not None,
                       level="DEBUG")
                summaries[-1]["consensus"] = comparisons
            if silver is not None and gold is not None:
                fresh = FreshKeyFacts(snapshot, silver, gold)
                record("trading.keys.facts.ready", source_sequence=barrier,
                       source_sequences=[item.sequence for item in samples["silver_key"][-2:]],
                       samples_attempted=attempts, consensus_seconds=perf_counter() - consensus_started,
                       silver_have=silver.have,
                       silver_need=silver.need, gold_have=gold.have, gold_need=gold.need)
                return fresh
        unavailable("samples_exhausted")
        return None
    except Exception as error:
        reason = "cancelled" if isinstance(error, RuntimeWaitCancelled) else "read_exception"
        if sample_detail is not None:
            sample_detail["exception_type"] = type(error).__name__
            record_sample("rejected", reason, current)
        unavailable(reason, exception_type=type(error).__name__,
                    exception_message=str(error))
        raise


def execute_productive_key_trade(*, operation, snapshot, row_fact, quantity,
                                 observer, actions, panel_reader, read_facts,
                                 cancel_requested, events=None, clock=monotonic):
    """Delegate UI callbacks to C4 and retain the consensus proving its effect."""
    from bot.trading_productive_operation import execute_productive_trade
    after_facts = None

    def read_row_fact(barrier):
        nonlocal after_facts
        after_facts = read_facts(barrier)
        if after_facts is None:
            return None
        return (after_facts.gold_fact if row_fact.item_id == "gold_key"
                else after_facts.silver_fact)

    def execute(**callbacks):
        return execute_key_trade(
            operation=operation, snapshot=snapshot, row_fact=row_fact,
            quantity=quantity, targets=panel_targets(), tap=None,
            cancel_requested=cancel_requested, **callbacks,
        )

    result = execute_productive_trade(
        snapshot=snapshot, row_fact=row_fact, quantity=quantity, observer=observer,
        actions=actions, panel_reader=panel_reader, read_row_fact=read_row_fact,
        row_ready=is_keys_ready, execute=execute,
        cancel_requested=cancel_requested, events=events, clock=clock,
    )
    record_best_effort(events, "trading.keys.trade.result", operation=operation.value,
                       outcome=result.outcome.value, reason=result.reason,
                       inputs=result.inputs, confirmed="tap_confirm" in result.inputs,
                       before_fact=vars(result.before_fact),
                       after_fact=vars(result.after_fact) if result.after_fact else None,
                       evidence=result.evidence)
    if after_facts is not None and result.outcome.value == "success":
        return VerifiedKeyTradeResult(**vars(result), fresh_key_facts=after_facts)
    return result
