from types import SimpleNamespace

from bot.catalog import SCREEN_BLACK_MARKET, SCREEN_LOBBY
from bot.runtime_observer import RuntimeWaitTimeout
from bot.state import ResolutionStatus
from tools.smoke_black_market_session import _wait_for_clean_lobby


def _snapshot(sequence, *, status, base=None, overlays=()):
    return SimpleNamespace(
        sequence=sequence,
        state=SimpleNamespace(
            status=status,
            base_context=base,
            overlays=tuple(overlays),
        ),
    )


class Observer:
    def __init__(self, initial, waited=None):
        self.initial = initial
        self.waited = waited
        self.wait_calls = []

    def observe(self):
        return self.initial

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        self.wait_calls.append((after_sequence, timeout, stable_for))
        if isinstance(self.waited, BaseException):
            raise self.waited
        assert condition(self.waited)
        assert not abort_if(self.waited)
        return self.waited


def test_lobby_probe_waits_passively_through_transient_unknown():
    observer = Observer(
        _snapshot(1, status=ResolutionStatus.UNKNOWN),
        _snapshot(2, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY),
    )

    assert _wait_for_clean_lobby(observer)
    assert observer.wait_calls == [(1, 2.0, 0.25)]


def test_lobby_probe_rejects_resolved_incompatible_state_without_waiting():
    observer = Observer(
        _snapshot(
            1,
            status=ResolutionStatus.RESOLVED,
            base=SCREEN_BLACK_MARKET,
        )
    )

    assert not _wait_for_clean_lobby(observer)
    assert observer.wait_calls == []


def test_lobby_probe_timeout_is_false_not_an_exception():
    observer = Observer(
        _snapshot(1, status=ResolutionStatus.UNKNOWN),
        RuntimeWaitTimeout(after_sequence=1, timeout=2.0, last_snapshot=None),
    )

    assert not _wait_for_clean_lobby(observer)
