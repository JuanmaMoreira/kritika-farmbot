"""Native Intermediate capture that previously stopped before economy OCR."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from bot.arena_flow import ArenaFlow
from bot.arena_flow_reader import ArenaFlowReader, ArenaFlowVisuals
from bot.arena_reader import ArenaDetector, crop
from bot.arena_semantics import ArenaDifficulty
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine

ROOT = Path(__file__).resolve().parents[1]
ENTRY = json.loads((ROOT/'tests/fixtures/arena_normal_native/manifest.json').read_text())['entries'][0]


@pytest.fixture
def native():
    path = ROOT/ENTRY['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ENTRY['sha256']
    image = cv2.imread(str(path))
    assert list(image.shape) == ENTRY['frame_shape']
    return image


@pytest.fixture
def visuals():
    return ArenaFlowVisuals()


def challenge_guard(visuals, difficulty):
    # Exercise the same requested-difficulty guard used before native economy.
    return ArenaFlow(SimpleNamespace(source=None), None,
                     SimpleNamespace(visuals=visuals), difficulty)._challenge


def test_native_intermediate_preparation(native, visuals):
    assert visuals.clean_challenge(native)
    facts = visuals.preparation(native)
    assert facts.difficulty is ArenaDifficulty.NORMAL
    assert facts.buffs == (False, False, False) and facts.x8 is True


@pytest.mark.parametrize('difficulty', list(ArenaDifficulty))
def test_native_guard_matches_only_requested_normal(native, visuals, difficulty):
    assert challenge_guard(visuals, difficulty)(native) is (difficulty is ArenaDifficulty.NORMAL)


def test_missing_title_does_not_infer_requested_difficulty(native, visuals):
    l, t, r, b = visuals._specs['difficulty_normal']['roi']
    crop(native, (l-.005, t-.007, r+.005, b+.007))[:] = 0
    assert visuals.clean_challenge(native)
    assert visuals.preparation(native).difficulty is None
    assert not challenge_guard(visuals, ArenaDifficulty.NORMAL)(native)


def test_default_detector_credits_normal(native):
    facts = {o.name: o.value for o in ArenaDetector().detect(native)}
    assert facts['fact.arena_difficulty'] == 'NORMAL'


def test_native_economy_reaches_real_ocr(native):
    reader = ArenaFlowReader(RapidOcrEngine(), clock=lambda:100.)
    facts = reader.economy(FrameSnapshot(native, 100., 1))
    assert facts is not None
    assert facts.available_badges == 106
    assert facts.preparation.difficulty is ArenaDifficulty.NORMAL
