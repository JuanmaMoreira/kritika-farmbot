"""Rotation R2-C (Quick Menu -> Character Select) stays global.

``rotation.open_character_select`` authorizes its only retry through
``QuickMenuHandoff.allows`` (fresh ``UNKNOWN/matching-origin + menu.quick``)
and aborts through ``handoff.observe`` plus
``_has_unexpected_character_select_transition``. A small detector subset
cannot tell a tolerated menu frame apart from a foreign contradiction:

- global: ``Guild + menu.quick`` is RESOLVED foreign -> abort;
- 2-detector scope (Character Select header + Quick Menu tile): the same
  frame is ``UNKNOWN + menu.quick`` -> retryable, abort lost.

With a valid handoff that degradation turns a terminal abort into an
erroneous bounded retry, so R2-C keeps the global observer
(G_JUSTIFIED). The nearest semantically equal subset would have to retain
every base/overlay rule dependency (B2-style resolver-complete, ~77/95
detectors): pseudo-global, no real value, not implemented.

These tests pin that justification on real frames with R2-C's exact
predicates. Timing (timeout 6 s, ``stable_for`` 1.0) and sentinel/scroll
contracts are untouched; wiring (R2-C runs on the global
``verified_transition``) is pinned by
``test_productive_rotation_scopes_only_post_swipe_and_r1_card_selection``.
"""

from pathlib import Path

import cv2
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_CHARACTER_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.observations import ObservationBatch
from bot.perception import (
    ROTATION_CHARACTER_SELECTION_SCOPE,
    build_default_perception,
    select_detectors,
)
from bot.quick_menu import DEFAULT_QUICK_MENU_POLICY, QuickMenuHandoff
from bot.rotation import (
    StandardRotation,
    _has_unexpected_character_select_transition,
    _is_clean_base,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import QuickMenuLayout
from bot.state import ResolutionStatus, ResolvedState

ROOT = Path(__file__).resolve().parents[1]
GUILD_QUICK_MENU = "screencaps/semantic/guild/quick-menu-from-guild/01.png"
LOBBY_QUICK_MENU = (
    "screencaps/semantic/workbench/20260825T193046_517947Z-76b5e238/"
    "frame-00002478.png"
)
CHARACTER_SELECT = (
    "screencaps/semantic/character_select/20260823T025400_922432Z.png"
)
FOREIGN_CLEAN = "screencaps/semantic/battle_mode_select/20260823T025716_783619Z.png"


def _frame(path):
    image = cv2.imread(str(ROOT / path))
    assert image is not None, path
    return FrameSnapshot(image=image, sequence=10, timestamp=10.0)


def _engines():
    perception = build_default_perception(ROOT)
    assert len(perception.detectors) == 96
    scoped = select_detectors(perception, ROTATION_CHARACTER_SELECTION_SCOPE)
    assert len(scoped.detectors) == 2
    return perception, scoped


def _snapshot(frame, state, sequence=10):
    return RuntimeSnapshot(
        frame=frame,
        observations=ObservationBatch(sequence=sequence, timestamp=float(sequence)),
        state=ResolvedState(
            status=state.status,
            sequence=sequence,
            timestamp=float(sequence),
            base_context=state.base_context,
            overlays=tuple(state.overlays),
            base_candidates=tuple(state.base_candidates),
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(frame.image),
    )


def _handoff(origin=SCREEN_LOBBY):
    layout = (
        QuickMenuLayout.LOBBY
        if origin == SCREEN_LOBBY
        else QuickMenuLayout.SHIFTED
    )
    return QuickMenuHandoff(origin, 1, 2, layout)


def _destination(snapshot):
    return _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)


def _r2c_abort(handoff, snapshot):
    """R2-C's exact abort predicate from ``StandardRotation._advance``."""
    return handoff.observe(snapshot, _destination) or (
        _has_unexpected_character_select_transition(
            snapshot, DEFAULT_QUICK_MENU_POLICY
        )
    )


def test_r2c_timing_contract_untouched():
    class _Observer:
        def observe(self):
            raise AssertionError("no observation expected")

        def wait_until(self, *args, **kwargs):
            raise AssertionError("no wait expected")

    class _Actions:
        def execute(self, action, geometry):
            raise AssertionError("no input expected")

    class _Events:
        def record(self, event, **fields):
            pass

    rotation = StandardRotation(_Observer(), _Actions(), _Events())
    assert rotation.transition_policy.normal_timeout == 6.0
    assert rotation.transition_policy.grace_timeout == 2.0
    assert rotation.transition_policy.max_attempts == 2
    assert rotation.scroll_profile.settle_for == 1.0


def test_global_aborts_on_foreign_resolved_menu():
    perception, _ = _engines()
    resolver = build_default_resolver()
    frame = _frame(GUILD_QUICK_MENU)
    state = resolver.resolve(perception.analyze(frame))
    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_GUILD
    assert tuple(state.overlays) == ("menu.quick",)
    handoff = _handoff(SCREEN_LOBBY)
    snapshot = _snapshot(frame, state)
    assert not _destination(snapshot)
    assert not handoff.allows(snapshot)
    assert _r2c_abort(handoff, snapshot)
    assert not handoff.valid


def test_two_detector_scope_degrades_foreign_menu_to_retryable_unknown():
    _, scoped = _engines()
    resolver = build_default_resolver()
    frame = _frame(GUILD_QUICK_MENU)
    state = resolver.resolve(scoped.analyze(frame))
    assert state.status is ResolutionStatus.UNKNOWN
    assert tuple(state.overlays) == ("menu.quick",)
    handoff = _handoff(SCREEN_LOBBY)
    snapshot = _snapshot(frame, state)
    assert not _destination(snapshot)
    # The contradiction signal is gone: the same frame that aborts
    # globally now looks like a tolerated menu wait that authorizes
    # exactly one bounded retry through the still-valid handoff.
    assert handoff.allows(snapshot)
    assert not _r2c_abort(handoff, snapshot)
    assert handoff.valid


def test_character_select_success_vocabulary_is_header_only():
    perception, scoped = _engines()
    resolver = build_default_resolver()
    frame = _frame(CHARACTER_SELECT)
    for engine in (perception, scoped):
        state = resolver.resolve(engine.analyze(frame))
        snapshot = _snapshot(frame, state)
        assert _destination(snapshot)
        assert not _r2c_abort(_handoff(SCREEN_LOBBY), snapshot)


def test_foreign_clean_screen_abort_is_lost_under_scope():
    perception, scoped = _engines()
    resolver = build_default_resolver()
    frame = _frame(FOREIGN_CLEAN)
    global_state = resolver.resolve(perception.analyze(frame))
    assert global_state.status is ResolutionStatus.RESOLVED
    assert global_state.base_context != SCREEN_CHARACTER_SELECT
    assert _r2c_abort(_handoff(SCREEN_LOBBY), _snapshot(frame, global_state))
    scoped_state = resolver.resolve(scoped.analyze(frame))
    assert scoped_state.status is ResolutionStatus.UNKNOWN
    assert not _r2c_abort(
        _handoff(SCREEN_LOBBY), _snapshot(frame, scoped_state)
    )


def test_post_input_source_menu_is_tolerated_not_aborted():
    perception, _ = _engines()
    resolver = build_default_resolver()
    frame = _frame(LOBBY_QUICK_MENU)
    state = resolver.resolve(perception.analyze(frame))
    assert tuple(state.overlays) == ("menu.quick",)
    handoff = _handoff(SCREEN_LOBBY)
    snapshot = _snapshot(frame, state)
    # The source menu may still be visible right after the tile input:
    # not success, not abort, retry only through the bounded loop.
    assert not _destination(snapshot)
    assert not _r2c_abort(handoff, snapshot)
    assert handoff.valid


def test_clean_source_without_menu_forbids_retry_on_stale_token():
    import numpy as np

    image = np.zeros((100, 200, 3), dtype=np.uint8)
    frame = FrameSnapshot(image=image, sequence=10, timestamp=10.0)
    handoff = _handoff(SCREEN_LOBBY)
    snapshot = _snapshot(
        frame,
        ResolvedState(
            status=ResolutionStatus.RESOLVED,
            sequence=10,
            timestamp=10.0,
            base_context=SCREEN_LOBBY,
            overlays=(),
            base_candidates=(),
        ),
    )
    # The tile had no visible effect yet and the menu is gone: the wait
    # may continue passively, but the stale token authorizes no retry.
    assert not _destination(snapshot)
    assert not _r2c_abort(handoff, snapshot)
    assert not handoff.valid
    assert not handoff.allows(snapshot)
