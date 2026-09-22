"""Board OCR and descriptive snapshot contracts; no device or gameplay input."""

from dataclasses import fields, replace
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import POPUP_SOCKET_INVENTORY_FULL, SCREEN_LOBBY
from bot.monster_wave_board_reader import (
    BOARD_ROWS, MonsterWaveBoardReader, MonsterWaveBoardRow,
    consensus_board_samples, parse_board_line,
)
from bot.monster_wave_board_snapshot import (
    BoardPopup, Tickets, build_monster_wave_board_snapshot,
    MonsterWaveBoardSnapshot,
)
from bot.monster_wave_semantics import (
    MW_BOARD, MW_CONTROLS_CLEAR, MW_MAX, MW_NEEDS_TICKETS,
    MW_PURCHASE_FULL, MW_SKIP_START, MW_TIMER, POPUP_MW_BOARD,
    POPUP_MW_PURCHASE, SCREEN_MONSTER_WAVE,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.ocr import RapidOcrEngine
from bot.ocr_extractors import RESOURCE_SAPPHIRES
from bot.runtime_facts import FactEvidence, FactQuality, RuntimeFact
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolvedState, ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "screencaps/semantic/monster-wave/board-g-current"
EXPECTED = (
    ("brawlers_badges", 258, 72),
    ("weapon_material", 412, 999),
    ("hero_weapon_material", 284, 999),
    ("bronze_key", 322, 499),
    ("silver_key", 129, 499),
)


def _snapshot(*, sequence=10, timestamp=None, names=(), overlays=(),
              base=SCREEN_MONSTER_WAVE, status=ResolutionStatus.RESOLVED,
              path=None):
    if timestamp is None:
        timestamp = float(sequence)
    image = cv2.imread(str(path)) if path else np.zeros((1224, 2712, 3), dtype=np.uint8)
    assert image is not None
    observations = tuple(Observation(name, 1.0, ObservationSource.LOCAL_CV) for name in names)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, observations),
        ResolvedState(status, sequence, timestamp, base_context=base if status is ResolutionStatus.RESOLVED else None,
                      overlays=overlays,
                      base_candidates=(SCREEN_MONSTER_WAVE, SCREEN_LOBBY)
                      if status is ResolutionStatus.AMBIGUOUS else ()),
        RuntimeFacts(), FrameGeometry.from_frame(image),
    )


@pytest.fixture(scope="module")
def reader():
    return MonsterWaveBoardReader(RapidOcrEngine())


def test_current_human_confirmed_board_exact_values_and_consensus(reader):
    samples = tuple(reader.read_sample(_snapshot(
        sequence=i, names=(MW_BOARD,), overlays=(POPUP_MW_BOARD,),
        path=CURRENT / f"{i:02}.png")) for i in (1, 2, 3))
    assert all(sample is not None for sample in samples)
    for sample in samples:
        assert tuple((row.item_id, row.balance, row.displayed_limit) for row in sample.rows) == EXPECTED
    fact = consensus_board_samples(samples[:2], after_sequence=0)
    assert fact is not None and fact.sample_sequences == (1, 2)
    board = build_monster_wave_board_snapshot(
        _snapshot(sequence=2, names=(MW_BOARD, MW_MAX, MW_SKIP_START),
                  overlays=(POPUP_MW_BOARD,), path=CURRENT / "02.png"),
        after_sequence=0, now=2.1, board_fact=fact,
    )
    assert board is not None
    assert board.board_popup is BoardPopup.PRESENT_WITH_ROWS
    assert board.resource_rows == fact.rows
    assert board.gold_key_capacity == "NOT_OBSERVABLE"
    assert board.tickets is Tickets.UNKNOWN
    assert board.max_state.selected is True
    assert board.evidence.row_sequences == (1, 2)


def test_context_guard_precedes_ocr(reader, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("OCR must not run outside board popup")
    monkeypatch.setattr(reader.engine, "recognize", forbidden)
    assert reader.read_sample(_snapshot(names=(MW_BOARD,), base=SCREEN_LOBBY)) is None
    assert reader.read_sample(_snapshot(names=(MW_BOARD,), status=ResolutionStatus.UNKNOWN)) is None
    assert reader.read_sample(_snapshot(names=(MW_BOARD,), status=ResolutionStatus.AMBIGUOUS)) is None
    assert reader.read_sample(_snapshot(names=(MW_BOARD,))) is None


@pytest.mark.parametrize("text,item_id", [
    ("(322/499) Silver Key", "bronze_key"),
    ("Bronze Key", "bronze_key"),
    ("(x/499) Bronze Key", "bronze_key"),
    ("(322/0) Bronze Key", "bronze_key"),
    ("(322/499) Bronze Keya", "bronze_key"),
])
def test_unreadable_or_wrong_line_never_becomes_zero(text, item_id):
    assert parse_board_line(text, item_id) is None


def test_balance_above_displayed_limit_is_read_as_shown():
    assert parse_board_line("(258/72) Brawler's Badges", "brawlers_badges") == (
        MonsterWaveBoardRow("brawlers_badges", 258, 72))


def test_consensus_rejects_changed_row_stale_and_contradictory_samples(reader):
    first = reader.read_sample(_snapshot(sequence=1, names=(MW_BOARD,),
        overlays=(POPUP_MW_BOARD,), path=CURRENT / "01.png"))
    second = reader.read_sample(_snapshot(sequence=2, names=(MW_BOARD,),
        overlays=(POPUP_MW_BOARD,), path=CURRENT / "02.png"))
    assert first is not None and second is not None
    altered = replace(second, rows=(MonsterWaveBoardRow("brawlers_badges", 0, 72), *second.rows[1:]))
    assert consensus_board_samples((first, altered), after_sequence=0) is None
    assert consensus_board_samples((first, second), after_sequence=1) is None
    assert consensus_board_samples((first, replace(second, sequence=1)), after_sequence=0) is None
    assert consensus_board_samples((first, replace(second, observed_at=1.0)), after_sequence=0) is None
    assert consensus_board_samples((first, replace(second, observed_at=3.0)), after_sequence=0) is None


def test_snapshot_rejects_foreign_or_prior_board_fact(reader):
    samples = tuple(reader.read_sample(_snapshot(
        sequence=i, names=(MW_BOARD,), overlays=(POPUP_MW_BOARD,),
        path=CURRENT / f"{i:02}.png")) for i in (1, 2))
    fact = consensus_board_samples(samples, after_sequence=0)
    assert fact is not None
    board = _snapshot(sequence=2, names=(MW_BOARD,), overlays=(POPUP_MW_BOARD,))
    for altered in (replace(fact, context=SCREEN_LOBBY),
                    replace(fact, popup=POPUP_MW_PURCHASE),
                    replace(fact, observed_at=1.0),
                    replace(fact, sequence=3, sample_sequences=(1, 3))):
        assert build_monster_wave_board_snapshot(
            board, after_sequence=0, now=2.1, board_fact=altered) is None
    assert build_monster_wave_board_snapshot(
        board, after_sequence=1, now=2.1, board_fact=fact) is None


def test_clean_board_snapshot_is_descriptive_and_has_no_rows():
    snap = _snapshot(names=(MW_TIMER, MW_SKIP_START, MW_CONTROLS_CLEAR, MW_MAX))
    board = build_monster_wave_board_snapshot(snap, after_sequence=9, now=10.1)
    assert board is not None
    assert board.board_popup is BoardPopup.ABSENT and board.resource_rows == ()
    assert board.skip_state.value == "active" and board.max_state.selected is True
    assert board.sapphires_daily is None and board.gold_key_capacity == "NOT_OBSERVABLE"


def test_foreign_unknown_ambiguous_stale_and_contradictory_context_fail_closed():
    names = (MW_TIMER, MW_SKIP_START, MW_CONTROLS_CLEAR)
    for snap in (
        _snapshot(names=names, base=SCREEN_LOBBY),
        _snapshot(names=names, status=ResolutionStatus.UNKNOWN),
        _snapshot(names=names, status=ResolutionStatus.AMBIGUOUS),
        _snapshot(names=(MW_BOARD, *names)),
        _snapshot(names=names, overlays=(POPUP_MW_BOARD,)),
        _snapshot(names=(MW_NEEDS_TICKETS, MW_TIMER, MW_SKIP_START)),
    ):
        assert build_monster_wave_board_snapshot(snap, after_sequence=9, now=10.1) is None
    snap = _snapshot(names=names)
    assert build_monster_wave_board_snapshot(snap, after_sequence=10, now=10.1) is None
    assert build_monster_wave_board_snapshot(snap, after_sequence=9, now=13.0) is None


def test_popup_without_confirmed_rows_describes_unknown_content():
    snap = _snapshot(names=(MW_BOARD,), overlays=(POPUP_MW_BOARD,))
    board = build_monster_wave_board_snapshot(snap, after_sequence=9, now=10.1)
    assert board is not None
    assert board.board_popup is BoardPopup.PRESENT_CONTENT_UNKNOWN
    assert board.resource_rows == ()


def test_existing_ticket_purchase_blocker_and_sapphire_facts_are_only_described():
    needs = build_monster_wave_board_snapshot(
        _snapshot(names=(MW_NEEDS_TICKETS, MW_CONTROLS_CLEAR)),
        after_sequence=9, now=10.1)
    assert needs is not None and needs.tickets is Tickets.NEEDS
    purchase = build_monster_wave_board_snapshot(
        _snapshot(names=(MW_PURCHASE_FULL,), overlays=(POPUP_MW_PURCHASE,)),
        after_sequence=9, now=10.1)
    assert purchase is not None and purchase.tickets is Tickets.PURCHASE_FULL
    blocker = build_monster_wave_board_snapshot(
        _snapshot(overlays=(POPUP_SOCKET_INVENTORY_FULL,)),
        after_sequence=9, now=10.1)
    assert blocker is not None and blocker.blockers == (POPUP_SOCKET_INVENTORY_FULL,)

    snap = _snapshot(names=(MW_NEEDS_TICKETS, MW_CONTROLS_CLEAR))
    fact = RuntimeFact(RESOURCE_SAPPHIRES, 0, 0.99, FactQuality.VALIDATED_SINGLE,
        ObservationSource.OCR, SCREEN_MONSTER_WAVE,
        (FactEvidence(10, 10.0, "0", 0.99),))
    with_sapphires = build_monster_wave_board_snapshot(
        snap, after_sequence=9, now=10.1, sapphires_fact=fact)
    assert with_sapphires is not None and with_sapphires.sapphires_daily == 0
    assert build_monster_wave_board_snapshot(
        snap, after_sequence=10, now=10.1, sapphires_fact=fact) is None
    assert build_monster_wave_board_snapshot(
        snap, after_sequence=9, now=10.1,
        sapphires_fact=replace(fact, context=SCREEN_LOBBY)) is None


def test_snapshot_schema_has_no_routing_and_modules_have_no_executor_imports():
    names = {field.name for field in fields(MonsterWaveBoardSnapshot)}
    assert {"skip_state", "tickets", "sapphires_daily", "max_state", "board_popup",
            "blockers", "resource_rows", "evidence", "gold_key_capacity"} == names
    for forbidden in ("route", "next_action", "should_visit_trading", "should_craft"):
        assert forbidden not in names
    source = "\n".join((ROOT / f"bot/{name}.py").read_text(encoding="utf-8")
                       for name in ("monster_wave_board_reader", "monster_wave_board_snapshot"))
    for forbidden in ("bot.trading", "bot.craft", "bot.treasure", "bot.equipment_relief",
                      "ActionExecutor", "AdbClient", ".tap(", ".execute("):
        assert forbidden not in source
    assert len(BOARD_ROWS) == 5
    snap = build_monster_wave_board_snapshot(
        _snapshot(names=(MW_NEEDS_TICKETS, MW_CONTROLS_CLEAR)),
        after_sequence=9, now=10.1)
    assert snap is not None
    with pytest.raises(ValueError, match="not observable"):
        replace(snap, gold_key_capacity="499")


def test_existing_monster_wave_corpus_context_gate(reader):
    manifest = json.loads((ROOT / "datasets/monster_wave_semantic_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 97
    historical_board = 0
    for sequence, entry in enumerate(manifest["entries"], 1):
        is_board = entry["overlays"] == [POPUP_MW_BOARD]
        names = (MW_BOARD,) if is_board else ()
        base = entry["base_context"]
        snap = _snapshot(sequence=sequence, names=names,
                         overlays=tuple(entry["overlays"]),
                         base=base if base != "unknown" else None,
                         status=ResolutionStatus.RESOLVED if base != "unknown" else ResolutionStatus.UNKNOWN,
                         path=ROOT / entry["path"])
        sample = reader.read_sample(snap)
        if is_board:
            historical_board += 1
        else:
            assert sample is None, entry["path"]
    assert historical_board == 6
