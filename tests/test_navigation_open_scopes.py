"""Scoped-first normal-path navigation transitions (Batch B1).

Migrates only positive known transitions to scoped perception, keeping
every retry/policy/timing identical:

1. Send Stamina ``OpenFriends`` -> SEND_STAMINA_COMPLETION_SCOPE (reuse, 3)
2. Mailbox ``OpenMailbox`` -> MAILBOX_CLAIM_SCOPE (reuse, 5)
3. Black Market ``open`` -> BLACK_MARKET_OPEN_SCOPE (new, 7)
4. Lobby -> Guild direct ``open_guild`` -> GUILD_NAVIGATE_SCOPE (new, 5)
5. BM ``reject_insufficient_gold`` -> BLACK_MARKET_SLOT_SCOPE (reuse, 6)

Daily ``OpenQuests`` was reverted to global after B1 HIL exposed a false
noop: panel chrome satisfies the navigation expected before the mission
list populates, and the claim/noop decision reads the open snapshot
directly. The DAILY_CLAIM_SCOPE itself (Claim All) is untouched and stays
validated here through the real-frame equivalence.

``open_quick_menu`` stays global on purpose: its retryable_from spans four
origin bases (Guild/PetsManage/PetSummon/WorldBoss) and scoping it would
either explode the vocabulary or silently drop the second attempt.

Closes to Lobby, select_lobby, postconditions and snapshot handoff are
untouched. Recovery/discovery stays global: scopes never fall back to
global inside a wait; foreign states degrade to bounded timeout with no
input authorized.
"""

import inspect
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.black_market_flow import (
    BlackMarketFlow,
    _has_incompatible_after_reject,
    _has_incompatible_navigation_state,
    _is_clean_base as _bm_is_clean_base,
    _is_insufficient_gold_popup,
)
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    MODE_DAILY_QUESTS,
    MODE_MAILBOX_CHARACTER_MAIL,
    POPUP_INSUFFICIENT_GOLD,
    SCREEN_BLACK_MARKET,
    SCREEN_FRIENDS,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_MAILBOX_CLAIMABLE,
    STATUS_MAILBOX_READ_MAIL_PRESENT,
    build_default_resolver,
)
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_black_market,
    _open_transition_for,
    scoped_transition_for,
)
from bot.guild_check_in_flow import _is_attendance_completed
from bot.mailbox_flow import (
    MailboxFlow,
    _has_incompatible_mailbox_navigation,
    _is_character_mail,
    _is_mailbox,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import (
    BLACK_MARKET_OPEN_SCOPE,
    BLACK_MARKET_OPEN_SCOPE_SPEC_NAMES,
    BLACK_MARKET_SLOT_SCOPE,
    DAILY_CLAIM_SCOPE,
    GUILD_NAVIGATE_SCOPE,
    GUILD_NAVIGATE_SCOPE_SPEC_NAMES,
    MAILBOX_CLAIM_SCOPE,
    SEND_STAMINA_COMPLETION_SCOPE,
    build_default_perception,
    select_detectors,
)
from bot.perception.black_market import (
    BlackMarketGoldDetector,
    BlackMarketPurchasedDetector,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.guild import GuildAttendanceDetector
from bot.perception.local_cv import LocalCvDetector
from bot.productive_runtime import (
    ProductiveRuntime,
    _has_quick_menu,
    _is_clean_base as _runtime_is_clean_base,
)
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.send_stamina_flow import (
    SendStaminaFlow,
    _has_incompatible_friends_navigation,
    _is_daily_active,
    _is_friends,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]


def _rows_observation():
    return Observation(
        "indicator.daily_quests_rows_populated",
        0.95,
        ObservationSource.LOCAL_CV,
    )


def _snapshot(
    sequence,
    timestamp,
    *,
    status,
    base=SCREEN_LOBBY,
    overlays=(),
    facts=None,
    observations=(),
):
    if status is not ResolutionStatus.RESOLVED:
        base = None
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(
            sequence=sequence, timestamp=timestamp,
            observations=tuple(observations),
        ),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=(),
        ),
        facts if facts is not None else RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _lobby(sequence=1, timestamp=1.0):
    return _snapshot(
        sequence, timestamp, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY
    )


class RecordingObserver:
    """Minimal observer double with a scripted wait_until replay."""

    def __init__(self, initial, script=()):
        self.initial = initial
        self.script = list(script)
        self.observe_calls = 0
        self.wait_calls = []

    def observe(self):
        self.observe_calls += 1
        return self.initial

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        cancel_requested=None,
        stable_for=0.0,
    ):
        self.wait_calls.append((timeout, stable_for))
        stable_since = None
        last = None
        for item in self.script:
            last = item
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            if condition(item):
                if stable_since is None:
                    stable_since = item.timestamp
                if item.timestamp - stable_since >= stable_for:
                    return item
            else:
                stable_since = None
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence, timeout=timeout, last_snapshot=last
        )


class Actions:
    def __init__(self):
        self.items = []

    def execute(self, action, geometry):
        self.items.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


# ---------------------------------------------------------------------------
# Composition: the two new scopes select exactly their declared vocabulary.
# ---------------------------------------------------------------------------


def test_black_market_open_scope_selects_exactly_seven_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, BLACK_MARKET_OPEN_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 7
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(BLACK_MARKET_OPEN_SCOPE_SPEC_NAMES)
    assert "landmark.lobby_trading_center_label" in local_names
    assert "landmark.black_market_title" in local_names
    assert sum(isinstance(item, BlackMarketGoldDetector) for item in scoped.detectors) == 1
    assert (
        sum(isinstance(item, BlackMarketPurchasedDetector) for item in scoped.detectors)
        == 1
    )
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_guild_navigate_scope_selects_exactly_five_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, GUILD_NAVIGATE_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 5
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(GUILD_NAVIGATE_SCOPE_SPEC_NAMES)
    assert "landmark.lobby_trading_center_label" in local_names
    assert "landmark.quick_menu_lobby_tile" in local_names
    assert (
        sum(isinstance(item, GuildAttendanceDetector) for item in scoped.detectors)
        == 1
    )
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_new_scopes_fail_fast_on_missing_detectors():
    source = build_default_perception(ROOT)
    with pytest.raises(ValueError):
        select_detectors(PerceptionEngine(detectors=()), BLACK_MARKET_OPEN_SCOPE)
    with pytest.raises(ValueError):
        select_detectors(PerceptionEngine(detectors=()), GUILD_NAVIGATE_SCOPE)
    local_only = PerceptionEngine(
        detectors=tuple(
            detector
            for detector in source.detectors
            if isinstance(detector, LocalCvDetector)
        )
    )
    with pytest.raises(ValueError):
        select_detectors(local_only, BLACK_MARKET_OPEN_SCOPE)
    with pytest.raises(ValueError):
        select_detectors(local_only, GUILD_NAVIGATE_SCOPE)


def test_reused_scopes_cover_the_open_predicates():
    # Reuse is semantic, not coincidental: the open waits decide on exactly
    # the observations these scopes were built for.
    assert set(SEND_STAMINA_COMPLETION_SCOPE.spec_names) == {
        "landmark.friends_title",
        "landmark.friends_all_button",
        "indicator.friends_send_stamina_daily_active",
    }
    assert SEND_STAMINA_COMPLETION_SCOPE.specialized_types == ()
    assert {
        "landmark.mailbox_title",
        "landmark.mailbox_character_mail_active",
        "landmark.mailbox_row_claim_button",
        "landmark.mailbox_row_delete_button",
    } <= set(MAILBOX_CLAIM_SCOPE.spec_names)
    assert {
        "landmark.daily_quests_title",
        "landmark.daily_quests_tab_active",
        "landmark.daily_quests_row_claim_button",
    } <= set(DAILY_CLAIM_SCOPE.spec_names)
    assert {
        "landmark.black_market_title",
        "landmark.purchase_confirmation_prompt",
        "landmark.insufficient_gold_prompt",
        "landmark.inventory_full_ok_button",
    } <= set(BLACK_MARKET_SLOT_SCOPE.spec_names)


# ---------------------------------------------------------------------------
# Contract: expected / retryable / abort / UNKNOWN safety per migrated wait.
# ---------------------------------------------------------------------------


def test_open_friends_contract():
    friends = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_FRIENDS,
        overlays=(STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,),
    )
    assert _is_friends(friends)
    assert _is_daily_active(friends)
    assert not _has_incompatible_friends_navigation(friends)

    settled = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_FRIENDS
    )
    assert _is_friends(settled)
    assert not _has_incompatible_friends_navigation(settled)

    # Clean Lobby is the pre-tap source, never an abort: the tap may simply
    # not have landed yet, and this wait has no retry to protect.
    assert not _has_incompatible_friends_navigation(_lobby())
    assert not _is_friends(_lobby())

    foreign = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_QUESTS,
    )
    assert _has_incompatible_friends_navigation(foreign)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _is_friends(unknown)
    assert not _has_incompatible_friends_navigation(unknown)


def test_open_mailbox_contract_and_carry():
    mailbox = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_MAILBOX,
        overlays=(MODE_MAILBOX_CHARACTER_MAIL, STATUS_MAILBOX_CLAIMABLE),
    )
    assert _is_mailbox(mailbox)
    assert _is_character_mail(mailbox)
    assert not _has_incompatible_mailbox_navigation(mailbox)

    assert not _has_incompatible_mailbox_navigation(_lobby())
    assert not _is_mailbox(_lobby())

    foreign = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_FRIENDS
    )
    assert _has_incompatible_mailbox_navigation(foreign)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _is_mailbox(unknown)
    assert not _has_incompatible_mailbox_navigation(unknown)


def test_open_quests_contract():
    quests = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
    )
    assert DailyQuestsFlow._is_quests(quests)
    assert DailyQuestsFlow._is_daily_quests(quests)
    assert not DailyQuestsFlow._has_incompatible_daily_navigation(quests)

    assert not DailyQuestsFlow._has_incompatible_daily_navigation(_lobby())
    assert not DailyQuestsFlow._is_quests(_lobby())

    foreign = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_FRIENDS
    )
    assert DailyQuestsFlow._has_incompatible_daily_navigation(foreign)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not DailyQuestsFlow._is_quests(unknown)
    assert not DailyQuestsFlow._has_incompatible_daily_navigation(unknown)


def test_black_market_open_contract_retryable_needs_lobby():
    market = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET
    )
    assert _bm_is_clean_base(market, SCREEN_BLACK_MARKET)
    assert not _has_incompatible_navigation_state(market)

    lobby = _lobby(2, 2.0)
    assert _bm_is_clean_base(lobby, SCREEN_LOBBY)
    assert not _has_incompatible_navigation_state(lobby)

    popup = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_BLACK_MARKET,
        overlays=(POPUP_INSUFFICIENT_GOLD,),
    )
    assert _has_incompatible_navigation_state(popup)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _bm_is_clean_base(unknown, SCREEN_BLACK_MARKET)
    assert not _has_incompatible_navigation_state(unknown)


def test_reject_insufficient_gold_contract():
    popup = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_BLACK_MARKET,
        overlays=(POPUP_INSUFFICIENT_GOLD,),
    )
    assert _is_insufficient_gold_popup(popup)
    market = _snapshot(
        3, 3.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET
    )
    assert _bm_is_clean_base(market, SCREEN_BLACK_MARKET)
    assert not _has_incompatible_after_reject(market)
    assert not _has_incompatible_after_reject(popup)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _is_insufficient_gold_popup(unknown)
    assert not _has_incompatible_after_reject(unknown)


def test_open_guild_contract_quick_menu_does_not_abort():
    from bot.catalog import STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE

    guild = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    assert _runtime_is_clean_base(guild, SCREEN_GUILD)

    from bot.productive_runtime import _has_incompatible_destination_state

    assert not _has_incompatible_destination_state(guild, SCREEN_LOBBY, SCREEN_GUILD)
    assert not _has_incompatible_destination_state(
        _lobby(2, 2.0), SCREEN_LOBBY, SCREEN_GUILD
    )

    quick = _snapshot(
        2, 2.0, status=ResolutionStatus.UNKNOWN, overlays=(MENU_QUICK,)
    )
    assert _has_quick_menu(quick)
    assert not _has_incompatible_destination_state(quick, SCREEN_LOBBY, SCREEN_GUILD)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _runtime_is_clean_base(unknown, SCREEN_GUILD)
    assert not _has_incompatible_destination_state(
        unknown, SCREEN_LOBBY, SCREEN_GUILD
    )


# ---------------------------------------------------------------------------
# Wiring: exactly the migrated waits run scoped; everything else stays put.
# ---------------------------------------------------------------------------


def test_send_stamina_open_uses_completion_observer_close_stays_global():
    lobby = _lobby(1, 1.0)
    friends_a = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_FRIENDS,
        overlays=(STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,),
    )
    friends_b = _snapshot(
        3,
        2.8,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_FRIENDS,
    )
    lobby_b = _lobby(4, 4.0)
    lobby_c = _lobby(5, 4.3)

    main = RecordingObserver(lobby, [lobby_b, lobby_c])
    scoped = RecordingObserver(lobby, [friends_a, friends_a, friends_b, friends_b])
    flow = SendStaminaFlow(main, Actions(), Events(), completion_observer=scoped)
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    # OpenFriends ran on the scoped observer; CloseFriends stayed global.
    assert scoped.wait_calls[0] == (6.0, 0.25)
    assert main.wait_calls == [(6.0, 0.25)]
    assert main.observe_calls == 1


def test_mailbox_open_uses_claim_observer_rest_stays_global():
    lobby = _lobby(1, 1.0)
    mailbox = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_MAILBOX,
        overlays=(MODE_MAILBOX_CHARACTER_MAIL,),
    )
    mailbox_b = _snapshot(
        3,
        2.8,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_MAILBOX,
        overlays=(MODE_MAILBOX_CHARACTER_MAIL,),
    )
    lobby_b = _lobby(4, 4.0)
    lobby_c = _lobby(5, 4.3)

    main = RecordingObserver(lobby, [lobby_b, lobby_c])
    scoped = RecordingObserver(lobby, [mailbox, mailbox_b])
    flow = MailboxFlow(main, Actions(), Events(), claim_observer=scoped)
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert scoped.wait_calls == [(6.0, 0.25)]
    assert main.wait_calls == [(6.0, 0.25)]


def test_daily_open_uses_readiness_scoped_wait():
    # Batch B1 HIL divergence: the chrome-only scoped OpenQuests wait
    # (~0.4 s) completed before the mission list populated, and the
    # claim/noop decision read that snapshot directly -> false noop. The
    # open wait now runs on the readiness scope and gates on rows-populated
    # without the loading ring; chrome without rows never satisfies it.
    lobby = _lobby(1, 1.0)
    chrome_bare = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS,),
    )
    opened = _snapshot(
        3,
        2.5,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS,),
        observations=(_rows_observation(),),
    )
    opened_b = _snapshot(
        4,
        2.8,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS,),
        observations=(_rows_observation(),),
    )
    lobby_b = _lobby(5, 4.0)
    lobby_c = _lobby(6, 4.3)

    main = RecordingObserver(lobby, [lobby_b, lobby_c])
    open_scoped = RecordingObserver(lobby, [chrome_bare, opened, opened_b])
    claim_scoped = RecordingObserver(lobby, [])
    flow = DailyQuestsFlow(
        main, Actions(), Events(), claim_observer=claim_scoped,
        open_observer=open_scoped,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert open_scoped.wait_calls == [(6.0, 0.25)]
    assert main.wait_calls == [(6.0, 0.25)]
    assert claim_scoped.wait_calls == []


def _verified(observer, actions, events):
    return VerifiedTransition(observer, actions, events, None)


def test_black_market_open_uses_open_transition_close_stays_global():
    lobby = _lobby(1, 1.0)
    gold = RuntimeFacts(gold_slots=frozenset({4}))
    market_a = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    market_b = _snapshot(
        3, 2.8, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    lobby_b = _lobby(4, 4.0)
    lobby_c = _lobby(5, 4.3)

    main = RecordingObserver(lobby, [lobby_b, lobby_c])
    scoped_open = RecordingObserver(lobby, [market_a, market_b])
    actions, events = Actions(), Events()
    flow = BlackMarketFlow(
        main,
        actions,
        events,
        verified_transition=_verified(main, actions, events),
        open_transition=_verified(scoped_open, actions, events),
    )
    result = flow.run(max_slot_attempts=0)

    assert result.status is FlowStatus.COMPLETED
    assert scoped_open.wait_calls == [(5.0, 0.75)]
    assert main.wait_calls == [(5.0, 0.25)]
    assert len(actions.items) == 2


def test_black_market_reject_uses_slot_transition():
    lobby = _lobby(1, 1.0)
    gold = RuntimeFacts(gold_slots=frozenset({4}))
    market_a = _snapshot(
        2, 2.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    market_b = _snapshot(
        3, 2.8, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    popup = _snapshot(
        4,
        4.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_BLACK_MARKET,
        overlays=(POPUP_INSUFFICIENT_GOLD,),
        facts=gold,
    )
    clean_a = _snapshot(
        5, 5.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    clean_b = _snapshot(
        6, 5.6, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    lobby_b = _lobby(7, 7.0)
    lobby_c = _lobby(8, 7.3)

    main = RecordingObserver(lobby, [lobby_b, lobby_c])
    scoped_open = RecordingObserver(lobby, [market_a, market_b])
    scoped_slot = RecordingObserver(market_a, [popup, clean_a, clean_b])
    actions, events = Actions(), Events()
    flow = BlackMarketFlow(
        main,
        actions,
        events,
        verified_transition=_verified(main, actions, events),
        slot_transition=_verified(scoped_slot, actions, events),
        purchase_transition=_verified(main, actions, events),
        open_transition=_verified(scoped_open, actions, events),
    )
    result = flow.run(max_slot_attempts=1)

    assert result.status is FlowStatus.COMPLETED
    # select_slot (1.0/2.0, no stable) + reject (5.0/0.5) ran scoped.
    assert scoped_slot.wait_calls == [(1.0, 0.0), (5.0, 0.5)]
    # Only the final close ran on the global transition.
    assert main.wait_calls == [(5.0, 0.25)]


def test_registry_wires_open_transition_scoped_with_fallback():
    from bot.perception import build_default_perception as _build

    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8), timestamp=1.0, sequence=1
    )

    class FakeSource:
        def __init__(self, frame):
            self.frame = frame

        def get_frame(self):
            return frame

    events = Events()
    main_observer = RuntimeObserver(
        FakeSource(frame), _build(ROOT), build_default_resolver(), events=events
    )
    actions = Actions()
    main_transition = VerifiedTransition(main_observer, actions, events, None)

    class Dependencies:
        def __init__(self):
            self.observer = main_observer
            self.actions = actions
            self.events = events
            self.cancel_requested = lambda: False

    scoped = _open_transition_for(Dependencies(), main_transition)
    assert scoped is not main_transition
    assert len(scoped.observer.perception.detectors) == 7
    assert any(
        event == "black_market.open_scope_active" for event, _ in events.items
    )

    broken = SimpleNamespace(observer=object(), actions=actions, events=Events())
    assert _open_transition_for(broken, main_transition) is main_transition


def test_registry_builds_black_market_with_open_transition():
    from bot.flow_registry import _slot_transition_for

    events = Events()
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8), timestamp=1.0, sequence=1
    )

    class FakeSource:
        def __init__(self, frame):
            self.frame = frame

        def get_frame(self):
            return frame

    main_observer = RuntimeObserver(
        FakeSource(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )

    class Dependencies:
        def __init__(self):
            self.observer = main_observer
            self.actions = Actions()
            self.events = events
            self.cancel_requested = lambda: False

    flow = _build_black_market(Dependencies())
    assert isinstance(flow, BlackMarketFlow)
    assert flow.open_transition is not flow.verified_transition
    assert len(flow.open_transition.observer.perception.detectors) == 7
    assert flow.slot_transition is not flow.verified_transition
    assert _slot_transition_for is not None


def _runtime_stub(main_observer, scoped_observer):
    actions, events = Actions(), Events()
    stub = SimpleNamespace(
        observer=main_observer,
        actions=actions,
        events=events,
        cancel_requested=lambda: False,
    )
    stub.build_verified_transition = lambda: VerifiedTransition(
        main_observer, actions, events, None
    )
    return stub, actions, events


class ScopedMainObserver(RecordingObserver):
    def __init__(self, initial, script=(), scoped=None):
        super().__init__(initial, script)
        self._scoped = scoped
        self.perception = build_default_perception(ROOT)
        if scoped is not None:
            scoped.perception = self.perception

    def scoped(self, perception):
        self._scoped.perception = perception
        return self._scoped


def test_lobby_to_guild_open_runs_scoped_with_identical_policy():
    lobby = _lobby(1, 1.0)
    guild_a = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    guild_b = _snapshot(
        3,
        2.3,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    scoped = RecordingObserver(lobby, [guild_a, guild_b])
    main = ScopedMainObserver(lobby, [], scoped=scoped)
    stub, actions, events = _runtime_stub(main, scoped)

    assert ProductiveRuntime._navigate_lobby_to_guild(stub) is True
    # One scoped wait with the exact historical timeout/stable_for.
    assert scoped.wait_calls == [(6.0, 0.25)]
    assert main.wait_calls == []
    assert len(actions.items) == 1
    assert any(
        event == "precondition.guild_navigate_scope_active" for event, _ in events.items
    )
    count = next(
        fields["detector_count"]
        for event, fields in events.items
        if event == "precondition.guild_navigate_scope_active"
    )
    assert count == 5


def test_lobby_to_guild_falls_back_to_global_without_scoping():
    lobby = _lobby(1, 1.0)
    guild_a = _snapshot(
        2,
        2.0,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    guild_b = _snapshot(
        3,
        2.3,
        status=ResolutionStatus.RESOLVED,
        base=SCREEN_GUILD,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    main = RecordingObserver(lobby, [guild_a, guild_b])
    stub, actions, events = _runtime_stub(main, None)
    # No scoped()/perception seam: identical behavior on the main observer.
    assert ProductiveRuntime._navigate_lobby_to_guild(stub) is True
    assert main.wait_calls == [(6.0, 0.25)]
    assert len(actions.items) == 1


def test_wiring_uses_generic_infra_only():
    import bot.flow_registry as registry

    source = inspect.getsource(registry._open_transition_for)
    assert "scoped_transition_for" in source
    assert "BLACK_MARKET_OPEN_SCOPE" in source
    assert "VerifiedTransition(" not in source

    runtime_source = inspect.getsource(ProductiveRuntime._navigate_lobby_to_guild)
    assert "scoped_transition_for" in runtime_source
    assert "GUILD_NAVIGATE_SCOPE" in runtime_source

    for path in (
        "bot/send_stamina_flow.py",
        "bot/mailbox_flow.py",
        "bot/daily_quests_flow.py",
        "bot/black_market_flow.py",
        "bot/productive_runtime.py",
    ):
        text = (ROOT / path).read_text()
        assert "build_default_perception" not in text or path == "bot/productive_runtime.py"


# ---------------------------------------------------------------------------
# Retry: attempts stay scoped with identical policy and action counts.
# ---------------------------------------------------------------------------


class ScriptedObserver(RecordingObserver):
    """Observer double with an explicit wait_until side-effect script."""

    def __init__(self, initial, effects, fresh=()):
        super().__init__(initial, [])
        self.effects = list(effects)
        self.fresh = list(fresh)

    def observe(self):
        self.observe_calls += 1
        if self.fresh:
            return self.fresh.pop(0)
        return self.initial

    def wait_until(self, condition, **kwargs):
        self.wait_calls.append((kwargs["timeout"], kwargs["stable_for"]))
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def test_black_market_open_retry_stays_scoped():
    lobby = _lobby(1, 1.0)
    gold = RuntimeFacts(gold_slots=frozenset({4}))
    market_a = _snapshot(
        10, 10.0, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    market_b = _snapshot(
        11, 10.8, status=ResolutionStatus.RESOLVED, base=SCREEN_BLACK_MARKET, facts=gold
    )
    scoped = ScriptedObserver(
        lobby,
        [
            RuntimeWaitTimeout(after_sequence=1, timeout=5.0, last_snapshot=lobby),
            RuntimeWaitTimeout(after_sequence=1, timeout=2.0, last_snapshot=lobby),
            market_a,
            market_b,
        ],
        fresh=[_lobby(2, 3.0)],
    )
    actions, events = Actions(), Events()
    transition = VerifiedTransition(scoped, actions, events, None)
    from bot.verified_transition import VerifiedTransitionPolicy

    result = transition.execute(
        "black_market.open",
        _open_action(),
        lobby,
        expected=lambda snapshot: _bm_is_clean_base(snapshot, SCREEN_BLACK_MARKET),
        precondition=lambda snapshot: _bm_is_clean_base(snapshot, SCREEN_LOBBY),
        retryable_from=lambda snapshot: _bm_is_clean_base(snapshot, SCREEN_LOBBY),
        abort_if=_has_incompatible_navigation_state,
        stable_for=0.75,
        policy=VerifiedTransitionPolicy(
            normal_timeout=5.0, grace_timeout=2.0, max_attempts=2
        ),
    )

    assert result.succeeded
    assert result.attempt_count == 2
    # normal + grace + retry normal, all scoped, then no global fallback.
    assert scoped.wait_calls == [(5.0, 0.75), (2.0, 0.75), (5.0, 0.75)]
    assert scoped.observe_calls == 1
    assert len(actions.items) == 2


def _open_action():
    from bot.semantic_actions import OpenBlackMarket

    return OpenBlackMarket()


# ---------------------------------------------------------------------------
# Equivalence on real frames: global vs scoped, same predicates and carry.
# ---------------------------------------------------------------------------


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None, frame_path
    frame = FrameSnapshot(image=image, timestamp=float(sequence), sequence=sequence)
    batch = engine.analyze(frame)
    return (
        RuntimeSnapshot(
            frame=frame,
            observations=batch,
            state=resolver.resolve(batch),
            facts=_facts_from(batch),
            geometry=FrameGeometry.from_frame(image),
        ),
        batch,
    )


def _assert_same_resolution(global_snapshot, scoped_snapshot, name):
    assert (
        scoped_snapshot.state.status,
        scoped_snapshot.state.base_context,
    ) == (
        global_snapshot.state.status,
        global_snapshot.state.base_context,
    ), name
    assert tuple(scoped_snapshot.state.overlays) == tuple(
        global_snapshot.state.overlays
    ), name


FRIENDS_FRAMES = {
    "daily-active/01": "screencaps/semantic/daily_activity/friends/daily-active/01.png",
    "daily-inactive/01": "screencaps/semantic/daily_activity/friends/daily-inactive/01.png",
    "transition/last-active": "screencaps/semantic/daily_activity/friends/transition/01-last-active.png",
    "transition/first-inactive": "screencaps/semantic/daily_activity/friends/transition/02-first-inactive.png",
    "close-lobby/01": "screencaps/semantic/daily_activity/friends/close-lobby/01.png",
}

MAILBOX_FRAMES = {
    "character-claimable/01": "screencaps/semantic/daily-quests-mailbox/mailbox-character-claimable/01.png",
    "account/01": "screencaps/semantic/daily-quests-mailbox/mailbox-account/01.png",
    "read/01": "screencaps/semantic/daily-quests-mailbox/mailbox-read/01.png",
    "processing/01": "screencaps/semantic/daily-quests-mailbox/mailbox-processing/01.png",
    "lobby/after-mailbox": "screencaps/semantic/daily-quests-mailbox/lobby/after-mailbox.png",
}

DAILY_FRAMES = {
    "claimable/01": "screencaps/semantic/daily-quests-mailbox/daily-claimable/01.png",
    "settled/01": "screencaps/semantic/daily-quests-mailbox/daily-settled/01.png",
    "progress-claim/01": "screencaps/semantic/daily-quests-mailbox/daily-progress-claim/01.png",
    "lobby/before-daily": "screencaps/semantic/daily-quests-mailbox/lobby/before-daily.png",
}

BLACK_MARKET_FRAMES = {
    "clean": "screencaps/semantic/black_market_currency/20260825T204554_063659Z.png",
    "insufficient": "screencaps/semantic/black_market_currency/20260825T204903_103690Z.png",
    "lobby": "screencaps/semantic/lobby/20260823T025455_304538Z.png",
}

GUILD_NAV_FRAMES = {
    "lobby-route/01": "screencaps/semantic/guild/lobby-route/01.png",
    "completed/01": "screencaps/semantic/guild/completed/01.png",
    "quick-menu-from-guild/01": "screencaps/semantic/guild/quick-menu-from-guild/01.png",
}


def test_scoped_matches_global_on_friends_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, SEND_STAMINA_COMPLETION_SCOPE)
    resolver = build_default_resolver()

    in_vocab = {k: v for k, v in FRIENDS_FRAMES.items() if k != "close-lobby/01"}
    for name, path in in_vocab.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        _assert_same_resolution(global_snapshot, scoped_snapshot, name)
        assert _is_friends(scoped_snapshot) == _is_friends(global_snapshot), name
        assert _is_daily_active(scoped_snapshot) == _is_daily_active(
            global_snapshot
        ), name
        assert _has_incompatible_friends_navigation(
            scoped_snapshot
        ) == _has_incompatible_friends_navigation(global_snapshot), name

    active, _ = _wrap(FRIENDS_FRAMES["daily-active/01"], scoped, resolver, sequence=1)
    assert _is_friends(active) and _is_daily_active(active)

    # The Lobby source is outside the completion vocabulary: it degrades to
    # UNKNOWN, which neither satisfies expected nor aborts. Same terminal
    # outcome (bounded timeout, no input) as waiting on a clean Lobby.
    lobby, _ = _wrap(FRIENDS_FRAMES["close-lobby/01"], scoped, resolver, sequence=1)
    assert lobby.state.status is ResolutionStatus.UNKNOWN
    assert not _is_friends(lobby)
    assert not _has_incompatible_friends_navigation(lobby)


def test_scoped_matches_global_on_mailbox_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, MAILBOX_CLAIM_SCOPE)
    resolver = build_default_resolver()

    in_vocab = {k: v for k, v in MAILBOX_FRAMES.items() if not k.startswith("lobby/")}
    for name, path in in_vocab.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        _assert_same_resolution(global_snapshot, scoped_snapshot, name)
        assert _is_mailbox(scoped_snapshot) == _is_mailbox(global_snapshot), name
        assert _is_character_mail(scoped_snapshot) == _is_character_mail(
            global_snapshot
        ), name
        assert _has_incompatible_mailbox_navigation(
            scoped_snapshot
        ) == _has_incompatible_mailbox_navigation(global_snapshot), name

    claimable, _ = _wrap(
        MAILBOX_FRAMES["character-claimable/01"], scoped, resolver, sequence=1
    )
    assert STATUS_MAILBOX_CLAIMABLE in claimable.state.overlays
    read, _ = _wrap(MAILBOX_FRAMES["read/01"], scoped, resolver, sequence=1)
    assert STATUS_MAILBOX_READ_MAIL_PRESENT in read.state.overlays

    # Lobby outside the claim vocabulary degrades to UNKNOWN: no expected,
    # no abort, bounded timeout with no input.
    lobby, _ = _wrap(MAILBOX_FRAMES["lobby/after-mailbox"], scoped, resolver, sequence=1)
    assert lobby.state.status is ResolutionStatus.UNKNOWN
    assert not _is_mailbox(lobby)
    assert not _has_incompatible_mailbox_navigation(lobby)


def test_scoped_matches_global_on_daily_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, DAILY_CLAIM_SCOPE)
    resolver = build_default_resolver()

    in_vocab = {k: v for k, v in DAILY_FRAMES.items() if not k.startswith("lobby/")}
    for name, path in in_vocab.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        _assert_same_resolution(global_snapshot, scoped_snapshot, name)
        assert DailyQuestsFlow._is_quests(scoped_snapshot) == DailyQuestsFlow._is_quests(
            global_snapshot
        ), name
        assert DailyQuestsFlow._is_daily_quests(
            scoped_snapshot
        ) == DailyQuestsFlow._is_daily_quests(global_snapshot), name
        assert DailyQuestsFlow._has_incompatible_daily_navigation(
            scoped_snapshot
        ) == DailyQuestsFlow._has_incompatible_daily_navigation(global_snapshot), name

    claimable, _ = _wrap(DAILY_FRAMES["claimable/01"], scoped, resolver, sequence=1)
    assert STATUS_DAILY_QUESTS_CLAIMABLE in claimable.state.overlays
    progress, _ = _wrap(
        DAILY_FRAMES["progress-claim/01"], scoped, resolver, sequence=1
    )
    assert STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE in progress.state.overlays

    # Lobby outside the claim vocabulary degrades to UNKNOWN: no expected,
    # no abort, bounded timeout with no input.
    lobby, _ = _wrap(DAILY_FRAMES["lobby/before-daily"], scoped, resolver, sequence=1)
    assert lobby.state.status is ResolutionStatus.UNKNOWN
    assert not DailyQuestsFlow._is_quests(lobby)
    assert not DailyQuestsFlow._has_incompatible_daily_navigation(lobby)


def test_scoped_matches_global_on_black_market_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, BLACK_MARKET_OPEN_SCOPE)
    slot = select_detectors(full, BLACK_MARKET_SLOT_SCOPE)
    resolver = build_default_resolver()

    for name, path in BLACK_MARKET_FRAMES.items():
        global_snapshot, global_batch = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, scoped_batch = _wrap(path, scoped, resolver, sequence=1)
        slot_snapshot, _ = _wrap(path, slot, resolver, sequence=1)
        _assert_same_resolution(global_snapshot, scoped_snapshot, "open:" + name)
        assert _facts_from(scoped_batch) == _facts_from(global_batch), name
        assert _bm_is_clean_base(
            scoped_snapshot, SCREEN_BLACK_MARKET
        ) == _bm_is_clean_base(global_snapshot, SCREEN_BLACK_MARKET), name
        assert _is_insufficient_gold_popup(
            scoped_snapshot
        ) == _is_insufficient_gold_popup(global_snapshot), name
        assert _has_incompatible_navigation_state(
            scoped_snapshot
        ) == _has_incompatible_navigation_state(global_snapshot), name
        if name != "lobby":
            _assert_same_resolution(global_snapshot, slot_snapshot, "slot:" + name)
            assert _has_incompatible_after_reject(
                slot_snapshot
            ) == _has_incompatible_after_reject(global_snapshot), name

    # The slot scope (reused for reject) lacks the Lobby landmark: a Lobby
    # frame degrades to UNKNOWN there, which is neither the popup nor an
    # abort. Same terminal outcome, no input.
    slot_lobby, _ = _wrap(BLACK_MARKET_FRAMES["lobby"], slot, resolver, sequence=1)
    assert slot_lobby.state.status is ResolutionStatus.UNKNOWN
    assert not _is_insufficient_gold_popup(slot_lobby)
    assert not _has_incompatible_after_reject(slot_lobby)

    clean, _ = _wrap(BLACK_MARKET_FRAMES["clean"], scoped, resolver, sequence=1)
    assert _bm_is_clean_base(clean, SCREEN_BLACK_MARKET)
    assert clean.facts.gold_slots == frozenset({4, 6, 7})
    insufficient, _ = _wrap(
        BLACK_MARKET_FRAMES["insufficient"], scoped, resolver, sequence=1
    )
    assert _is_insufficient_gold_popup(insufficient)
    assert not _bm_is_clean_base(insufficient, SCREEN_BLACK_MARKET)
    lobby, _ = _wrap(BLACK_MARKET_FRAMES["lobby"], scoped, resolver, sequence=1)
    assert _bm_is_clean_base(lobby, SCREEN_LOBBY)


def test_scoped_matches_global_on_guild_nav_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, GUILD_NAVIGATE_SCOPE)
    resolver = build_default_resolver()
    from bot.productive_runtime import _has_incompatible_destination_state

    for name, path in GUILD_NAV_FRAMES.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        _assert_same_resolution(global_snapshot, scoped_snapshot, name)
        assert _runtime_is_clean_base(
            scoped_snapshot, SCREEN_GUILD
        ) == _runtime_is_clean_base(global_snapshot, SCREEN_GUILD), name
        assert _runtime_is_clean_base(
            scoped_snapshot, SCREEN_LOBBY
        ) == _runtime_is_clean_base(global_snapshot, SCREEN_LOBBY), name
        assert _has_incompatible_destination_state(
            scoped_snapshot, SCREEN_LOBBY, SCREEN_GUILD
        ) == _has_incompatible_destination_state(
            global_snapshot, SCREEN_LOBBY, SCREEN_GUILD
        ), name

    quick, _ = _wrap(
        GUILD_NAV_FRAMES["quick-menu-from-guild/01"], scoped, resolver, sequence=1
    )
    assert _has_quick_menu(quick)
    assert not _has_incompatible_destination_state(quick, SCREEN_LOBBY, SCREEN_GUILD)
    assert _is_attendance_completed(quick) == _is_attendance_completed(
        _wrap(
            GUILD_NAV_FRAMES["quick-menu-from-guild/01"], full, resolver, sequence=1
        )[0]
    )
