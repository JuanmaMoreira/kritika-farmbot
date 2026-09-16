"""Trading Center context, tab state and content readiness (offline)."""

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center import (
    TradingTab,
    clean_trading,
    is_keys_content_ready,
    is_materials_content_ready,
    is_trading_screen,
    trading_tab,
)
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    INDICATOR_TRADING_MATERIAL_ROWS,
    LANDMARK_TRADING_CENTER_TITLE,
    SCREEN_TRADING,
)


def _observation(name, confidence=0.95):
    return Observation(name, confidence, ObservationSource.LOCAL_CV)


def _snapshot(sequence, timestamp, *, base, overlays=(), status=None,
               observations=(), candidates=()):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, tuple(observations)),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _trading(sequence, names=(), **kwargs):
    return _snapshot(
        sequence,
        float(sequence),
        base=SCREEN_TRADING,
        observations=[_observation(name) for name in names],
        **kwargs,
    )


def test_entry_context_verified_on_resolved_trading():
    assert is_trading_screen(_trading(1))
    assert clean_trading(_trading(1))


def test_entry_context_rejected_off_trading():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    assert not is_trading_screen(lobby)
    assert not clean_trading(lobby)
    assert not is_materials_content_ready(lobby)
    assert not is_keys_content_ready(lobby)


def test_overlays_break_clean_context():
    assert not clean_trading(_trading(1, overlays=("popup.unacquired",)))
    assert not is_materials_content_ready(
        _trading(1, (INDICATOR_TRADING_GENERAL_ACTIVE, INDICATOR_TRADING_MATERIAL_ROWS),
                 overlays=("popup.unacquired",))
    )


def test_tab_active_vs_merely_visible():
    general = _trading(1, (INDICATOR_TRADING_GENERAL_ACTIVE,))
    assert trading_tab(general) is TradingTab.GENERAL
    bare = _trading(2)
    assert trading_tab(bare) is TradingTab.UNKNOWN
    keys = _trading(3, (INDICATOR_TRADING_KEYS_ACTIVE,))
    assert trading_tab(keys) is TradingTab.KEYS


def test_low_confidence_tab_chrome_is_not_active():
    weak = _snapshot(
        1,
        1.0,
        base=SCREEN_TRADING,
        observations=[Observation(
            INDICATOR_TRADING_GENERAL_ACTIVE, 0.10, ObservationSource.LOCAL_CV
        )],
    )
    assert trading_tab(weak) is TradingTab.UNKNOWN


def test_content_not_ready_without_positive_rows_signal():
    assert not is_materials_content_ready(
        _trading(1, (INDICATOR_TRADING_GENERAL_ACTIVE,))
    )
    assert not is_keys_content_ready(
        _trading(2, (INDICATOR_TRADING_KEYS_ACTIVE,))
    )


def test_materials_content_ready_needs_general_plus_rows():
    ready = _trading(
        1, (INDICATOR_TRADING_GENERAL_ACTIVE, INDICATOR_TRADING_MATERIAL_ROWS)
    )
    assert is_materials_content_ready(ready)
    assert not is_keys_content_ready(ready)


def test_keys_content_ready_needs_keys_plus_rows():
    ready = _trading(
        1, (INDICATOR_TRADING_KEYS_ACTIVE, INDICATOR_TRADING_KEYS_ROWS)
    )
    assert is_keys_content_ready(ready)
    assert not is_materials_content_ready(ready)


def test_foreign_and_contradictory_context_authorize_nothing():
    both = _trading(
        1, (INDICATOR_TRADING_GENERAL_ACTIVE, INDICATOR_TRADING_KEYS_ACTIVE)
    )
    assert trading_tab(both) is TradingTab.CONTRADICTORY
    assert not is_materials_content_ready(both)
    assert not is_keys_content_ready(both)
    foreign = _snapshot(
        2, 2.0, base=SCREEN_LOBBY,
        observations=[_observation(INDICATOR_TRADING_GENERAL_ACTIVE)],
    )
    assert trading_tab(foreign) is TradingTab.UNKNOWN
    assert not is_materials_content_ready(foreign)


def test_unknown_and_ambiguous_never_authorize():
    unknown = _snapshot(1, 1.0, base=None, status=ResolutionStatus.UNKNOWN)
    assert not is_trading_screen(unknown)
    assert trading_tab(unknown) is TradingTab.UNKNOWN
    assert not is_materials_content_ready(unknown)
    assert not is_keys_content_ready(unknown)
    ambiguous = _snapshot(
        2, 2.0, base=None, status=ResolutionStatus.AMBIGUOUS,
        candidates=(SCREEN_LOBBY, SCREEN_TRADING),
        observations=[
            _observation(INDICATOR_TRADING_GENERAL_ACTIVE),
            _observation(INDICATOR_TRADING_MATERIAL_ROWS),
        ],
    )
    assert not is_trading_screen(ambiguous)
    assert trading_tab(ambiguous) is TradingTab.UNKNOWN
    assert not is_materials_content_ready(ambiguous)
    assert not is_keys_content_ready(ambiguous)


def test_title_landmark_is_distinct_from_tab_and_rows():
    assert LANDMARK_TRADING_CENTER_TITLE not in (
        INDICATOR_TRADING_GENERAL_ACTIVE,
        INDICATOR_TRADING_KEYS_ACTIVE,
        INDICATOR_TRADING_KEYS_ROWS,
        INDICATOR_TRADING_MATERIAL_ROWS,
    )
