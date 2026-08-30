from collections import defaultdict
from pathlib import Path, PurePosixPath

import cv2

from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_MAILBOX_CLAIM_PROCESSING,
    MODE_DAILY_QUESTS,
    MODE_MAILBOX_CHARACTER_MAIL,
    SCREEN_MAILBOX,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_MAILBOX_CLAIMABLE,
    STATUS_MAILBOX_READ_MAIL_PRESENT,
    build_default_resolver,
)
from bot.observations import ObservationBatch
from bot.perception import MailboxClaimProcessingDetector, build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/daily_quests_mailbox_semantic_manifest.json"


def _entries_by_group():
    grouped = defaultdict(list)
    for entry in load_manifest(MANIFEST):
        grouped[PurePosixPath(entry.path).parent.name].append(entry)
    return grouped


def _read(entry):
    frame = cv2.imread(str(ROOT / entry.path), cv2.IMREAD_COLOR)
    assert frame is not None, entry.path
    return frame


def _resolve(entry, sequence=1):
    observations = build_default_perception(ROOT).analyze(
        FrameSnapshot(_read(entry), timestamp=float(sequence), sequence=sequence)
    ).observations
    state = build_default_resolver().resolve(
        ObservationBatch(sequence, float(sequence), observations)
    )
    return {item.name for item in observations}, state


def test_curated_representatives_resolve_the_confirmed_states():
    for sequence, group in enumerate(_entries_by_group().values(), start=1):
        entry = group[0]
        _, state = _resolve(entry, sequence)

        assert state.status is ResolutionStatus.RESOLVED, entry.path
        assert state.base_context == entry.base_context, entry.path
        assert state.overlays == entry.overlays, entry.path


def test_daily_row_claim_status_excludes_the_independent_progress_reward():
    grouped = _entries_by_group()
    _, claimable = _resolve(grouped["daily-claimable"][0])
    _, progress_reward = _resolve(grouped["daily-progress-claim"][0], 2)
    _, settled_noop = _resolve(grouped["daily-settled"][-1], 3)

    assert claimable.base_context == SCREEN_QUESTS
    assert {MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE} <= set(
        claimable.overlays
    )
    for state in (progress_reward, settled_noop):
        assert state.base_context == SCREEN_QUESTS
        assert MODE_DAILY_QUESTS in state.overlays
        assert STATUS_DAILY_QUESTS_CLAIMABLE not in state.overlays


def test_mailbox_processing_activity_is_scoped_and_stable_states_are_negative():
    grouped = _entries_by_group()
    detector = MailboxClaimProcessingDetector(asset_root=ROOT)

    for entry in grouped["mailbox-processing"]:
        names = {item.name for item in detector.detect(_read(entry))}
        assert ACTIVITY_MAILBOX_CLAIM_PROCESSING in names, entry.path

    for group_name in ("mailbox-character-claimable", "mailbox-read", "mailbox-leftovers", "lobby"):
        for entry in grouped[group_name]:
            assert detector.detect(_read(entry)) == (), entry.path


def test_mailbox_read_and_leftover_statuses_are_independent():
    grouped = _entries_by_group()
    _, read = _resolve(grouped["mailbox-read"][0])
    _, leftovers = _resolve(grouped["mailbox-leftovers"][0], 2)

    assert read.base_context == SCREEN_MAILBOX
    assert {MODE_MAILBOX_CHARACTER_MAIL, STATUS_MAILBOX_READ_MAIL_PRESENT} <= set(
        read.overlays
    )
    assert STATUS_MAILBOX_CLAIMABLE not in read.overlays

    assert leftovers.base_context == SCREEN_MAILBOX
    assert {MODE_MAILBOX_CHARACTER_MAIL, STATUS_MAILBOX_CLAIMABLE} <= set(
        leftovers.overlays
    )
    assert STATUS_MAILBOX_READ_MAIL_PRESENT not in leftovers.overlays
