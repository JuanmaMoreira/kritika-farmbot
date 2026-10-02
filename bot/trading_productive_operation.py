"""Fresh Item Trade callbacks shared by productive Keys and Materials C4."""
from time import monotonic
from bot.runtime_observer import RuntimeWaitTimeout
from bot.trading_operation import quantity_satisfied, resolve_quantity_target

def execute_productive_trade(*, snapshot, row_fact, quantity, observer, actions,
                             panel_reader, read_row_fact, row_ready, execute,
                             cancel_requested, events=None, clock=monotonic):
    """Supply fresh panel/row callbacks and typed input to the C4 executor."""
    from bot.semantic_actions import ConfirmTradingTrade

    panel_barrier = snapshot.sequence
    confirmed = False
    confirm_dispatched_at = None
    pre_max_panel = None
    max_dispatched_at = None
    expected_max = None
    after_row = None
    row_read_attempted = False

    def read_panel():
        nonlocal panel_barrier, pre_max_panel
        found = None
        last_valid = None

        def ready(item):
            nonlocal found, last_valid, after_row, row_read_attempted
            # A newer sequence can have been captured while ADB was still
            # dispatching MAX. It is not evidence of the resulting UI state.
            if (max_dispatched_at is not None and not confirmed
                    and item.timestamp <= max_dispatched_at):
                return False
            if (confirmed and item.timestamp <= confirm_dispatched_at):
                return False
            from bot.event_log import record_best_effort
            from time import perf_counter
            started = perf_counter()
            found = panel_reader.read_snapshot(item, after_sequence=panel_barrier)
            record_best_effort(events, "trading.panel.sample", sequence=item.sequence,
                              phase="post_confirm" if confirmed else ("post_max" if max_dispatched_at is not None else "pre_max"),
                              reader_seconds=perf_counter() - started,
                              diagnostic=getattr(panel_reader, "last_diagnostic", None),
                              accepted=found is not None)
            if found is None:
                if not confirmed or not row_ready(item):
                    return False
                # Closing Item Trade can expose unchanged rows before a
                # delayed rejection. Only an observed decrement proves effect.
                row_read_attempted = True
                after_row = read_row_fact(item.sequence)
                return (after_row is not None
                        and after_row.item_id == row_fact.item_id
                        and after_row.section == row_fact.section
                        and after_row.have < row_fact.have)
            last_valid = found
            if (found.shows_output_full or found.shows_insufficient
                    or found.shows_limit):
                return True
            if confirmed:
                # The old Item Trade can remain visible after dispatch while
                # the server responds. It proves neither success nor rejection.
                return False
            if max_dispatched_at is None:
                return True
            return (found.quantity is not None and expected_max is not None
                    and quantity_satisfied(quantity, expected_max,
                                           found.quantity[0]))

        try:
            observed = observer.wait_until(
                ready, after_sequence=panel_barrier, timeout=6.0,
                cancel_requested=cancel_requested,
            )
        except RuntimeWaitTimeout:
            if max_dispatched_at is None or confirmed or last_valid is None:
                return None
            # Return the last valid post-dispatch panel to C4. An unchanged
            # selection becomes max_no_effect only after the full wait.
            panel_barrier = last_valid.sequence
            return last_valid
        panel_barrier = observed.sequence
        if max_dispatched_at is None:
            pre_max_panel = found
        return found

    def read_row():
        return after_row if row_read_attempted else read_row_fact(panel_barrier)

    def act(intent):
        nonlocal confirmed, max_dispatched_at, expected_max, confirm_dispatched_at
        from bot.semantic_actions import SelectTradingMaximum

        if isinstance(intent, SelectTradingMaximum):
            if pre_max_panel is None:
                raise ValueError("MAX requires a verified pre-action panel")
            target, error = resolve_quantity_target(
                quantity, pre_max_panel, row_fact,
            )
            if error is not None or target is None:
                raise ValueError("MAX target is unavailable")
        actions.execute(
            intent, snapshot.geometry, events=events,
            source_sequence=panel_barrier,
        )
        if isinstance(intent, SelectTradingMaximum):
            expected_max = target
            max_dispatched_at = clock()
        if isinstance(intent, ConfirmTradingTrade):
            confirmed = True
            confirm_dispatched_at = clock()

    return execute(read_panel=read_panel, read_row=read_row, act=act)
