"""A1 keeps its capture bounds despite unrelated global detector latency."""

from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.catalog import BASE_CONTEXT_RULES, OVERLAY_RULES, build_default_resolver
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import _build_productive_monster_wave
from bot.monster_wave_board_snapshot import BoardPopup
from bot.monster_wave_semantics import (
    MW_BOARD, MW_CONTROLS_CLEAR, MW_MAX, MW_OBSERVATIONS, MW_SCREEN, MW_SKIP_START,
)
from bot.monster_wave_standalone import MonsterWaveBoardAcquisitionRuntime
from bot.observations import Observation, ObservationSource
from bot.perception import (
    MONSTER_WAVE_BOARD_ACQUISITION_SCOPE, build_default_perception, select_detectors,
)
from bot.runtime_observer import RuntimeObserver
from bot.preconditions import EnsureOutcome, EnsureResult
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.verified_transition import VerifiedTransition
from test_monster_wave_productive import _Harness, _Reader, _pending, ROWS
from test_productive_runtime import Events
from test_session import Rotation


def test_board_scope_keeps_all_resolver_dependencies_and_mw_facts():
    full = build_default_perception()
    scoped = select_detectors(full, MONSTER_WAVE_BOARD_ACQUISITION_SCOPE)
    names = {getattr(getattr(d, "spec", None), "name", None) for d in scoped.detectors}
    specialized = {
        "landmark.meteorites_main", "landmark.meteorites_detail", "activity.meteorites_loading",
        "indicator.daily_quests_progress_reward_claimable",
        "indicator.guild_attendance_active", "indicator.guild_attendance_completed",
        "indicator.pet_epic_available", "indicator.pet_epic_unavailable",
        "landmark.combine_context", "landmark.pet_combine_result",
        "landmark.pet_mass_evolve_confirmation",
    }
    required = {name for rule in (*BASE_CONTEXT_RULES, *OVERLAY_RULES)
                for name in rule.requires}
    assert required <= names | specialized
    assert set(MW_OBSERVATIONS) <= names
    assert len(scoped.detectors) < len(full.detectors)
    assert all(d in full.detectors for d in scoped.detectors)


def _timed_board_runtime(monkeypatch):
    clock = [1404.875]
    image = np.zeros((100, 200, 3), np.uint8)
    source = SimpleNamespace(sequence=4625)

    def get_frame():
        source.sequence += 30
        return FrameSnapshot(image, clock[0], source.sequence)

    source.get_frame = get_frame
    full = build_default_perception()
    visible = {MW_SCREEN, MW_SKIP_START, MW_MAX, MW_CONTROLS_CLEAR, MW_BOARD}
    # Model the actual 1.015 s gap: context work + unrelated slot reader.
    # Neither the clock nor the latency changes as a result of running WB.
    for detector in full.detectors:
        name = getattr(getattr(detector, "spec", None), "name", None)

        def detect(_image, name=name, detector=detector):
            if name == MW_BOARD:
                clock[0] += .600
            elif type(detector).__name__ == "BlackMarketGoldDetector":
                clock[0] += .415
            return ((Observation(name, 1.0, ObservationSource.LOCAL_CV),)
                    if name in visible else ())

        monkeypatch.setattr(detector, "detect", detect)
    observer = RuntimeObserver(
        source, full, build_default_resolver(), clock=lambda: clock[0],
        sleeper=lambda duration: clock.__setitem__(0, clock[0] + duration),
    )
    actions = ActionExecutor(Mock())
    dependencies = SimpleNamespace(
        observer=observer, actions=actions, events=Events(),
        cancel_requested=lambda: False, equipment_combine_relief=Mock(),
        socket_relief=Mock(),
    )
    # No OCR/model initialization or hardware in this wiring regression.
    monkeypatch.setattr("bot.ocr.RapidOcrEngine", lambda: Mock())
    harness = _Harness(first=_pending(4625))
    flow = _build_productive_monster_wave(
        dependencies, VerifiedTransition(observer, actions, dependencies.events),
        lambda: harness.flow().inner,
    )
    flow.boards.reader = _Reader()
    flow.boards.clock = lambda: clock[0]
    flow.clock = lambda: clock[0]
    return flow, harness, observer, clock, dependencies


def test_global_observer_reproduces_logged_spacing_failure_before_ocr(monkeypatch):
    flow, _, observer, clock, _ = _timed_board_runtime(monkeypatch)
    reader = Mock()
    old = MonsterWaveBoardAcquisitionRuntime(observer, reader, clock=lambda: clock[0])
    with pytest.raises(ValueError, match="mw_board_consensus_unavailable"):
        old.acquire(after_sequence=4625)
    reader.read_sample.assert_not_called()
    assert clock[0] == pytest.approx(1404.875 + 6 * 1.015)


def _completed_world_boss():
    # Execute the real WB activity through raid completion and Back to hub.
    from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, SCREEN_WORLD_BOSS_BATTLE
    from test_world_boss_flow import (
        auto_result, build_flow, fact_result, happy_inputs,
    )

    waits, observes, transitions = happy_inputs()
    auto = Mock()
    auto.ensure_on_quick.return_value = auto_result()
    flow, observer, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 443, 1, SCREEN_LOBBY),
        timer_read=fact_result("battle.timer_remaining", 60, 9, SCREEN_WORLD_BOSS_BATTLE),
        waits=waits, observes=observes, transitions=transitions, auto=auto,
    )
    # PreparedActivity starts in the hub; zone enter/leave belongs to SessionRunner.
    observer.waits.pop(0)
    driver.snapshots.pop(0)
    driver.outcomes.pop(0)
    assert observer.waits[0].state.base_context == SCREEN_BATTLE_MODE_SELECT
    return flow, driver


@pytest.mark.parametrize("after_wb", [False, True], ids=["mw_alone", "wb_then_mw"])
def test_session_completed_wb_then_mw_board_matches_standalone(monkeypatch, after_wb):
    from bot.component_contracts import ComponentRequirement
    from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY

    flow, harness, observer, _, dependencies = _timed_board_runtime(monkeypatch)
    scoped = flow.boards.observer
    assert scoped is not observer
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    original_perception = observer.perception
    acquired = []
    acquire = flow.boards.acquire

    def remember(**kwargs):
        result = acquire(**kwargs)
        acquired.append(result)
        harness.board = result
        return result

    flow.boards.acquire = remember
    # Economic input and CLEAR remain scripted; A1 and the planner are real.
    flow.navigation = harness
    # This harness scripts economic preparation; Lobby readiness has dedicated
    # real owner/binding tests in test_gold_farming.
    flow.entry_readiness = lambda: None
    flow.activity.cancel_requested = lambda: False
    flow.activity.observer = SimpleNamespace(observe=lambda: harness.clean.context)
    trace = []
    zone = SimpleNamespace(
        entry_requirement=ComponentRequirement.exact_state(SCREEN_LOBBY),
        hub_requirement=ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
        enter=Mock(return_value=FlowResult(FlowStatus.COMPLETED)),
        leave=Mock(return_value=FlowResult(FlowStatus.COMPLETED)),
    )
    flows = []
    if after_wb:
        wb, driver = _completed_world_boss()
        # Resource reading is scripted in this board-spacing regression. The
        # fake ensurer has no physical snapshot for prepared_precheck to inspect.
        flows.append(replace(wb.prepared(zone), precheck=wb.precheck))
    flows.append(flow.prepared(zone))
    preconditions = SimpleNamespace(
        ensure=lambda requirement: EnsureResult(
            EnsureOutcome.ALREADY_SATISFIED, requirement, None, None,
        ),
        current_satisfies_any=lambda requirements: True,
    )
    result = SessionRunner(
        SessionPlan.standard(flows=tuple(flows), rotation_strategy=Rotation(1, trace),
                             character_count=1),
        preconditions=preconditions, events=dependencies.events,
    ).run()
    assert result.status is SessionStatus.COMPLETED, result.failure_cause
    if after_wb:
        wb_result = result.character_results[0].flow_results[0]
        assert wb_result.raid_complete_detected
        assert driver.calls[-1][0] == "world_boss.return_to_battle_mode"
        completed = [fields["flow"] for event, fields in dependencies.events.items
                     if event == "flow.completed"]
        assert completed == ["world_boss", "monster_wave"]
    assert observer.perception is original_perception
    assert flow.activity is flow.inner.activity
    assert zone.enter.call_count == 1 + int(after_wb)
    zone.leave.assert_not_called()
    assert result.character_results[0].flow_results[-1].final_snapshot is harness.clean.context
    assert len(acquired) == 1
    board = acquired[0]
    assert board.snapshot.board_popup is BoardPopup.PRESENT_WITH_ROWS
    assert board.snapshot.resource_rows == ROWS
    assert board.snapshot.evidence.row_sequences[0] > 4625
    assert board.context.timestamp - 1404.875 == pytest.approx(.6)
    assert [call[0] for call in harness.calls] == ["prepare", "pass", "yes", "finish"]



def test_mw_treasure_visit_has_currency_detector_and_complete_resolver(monkeypatch):
    from bot.perception import TreasureContentDetector
    from bot.treasure_center import is_gold_keys_content_ready
    from bot.treasure_center_semantics import (
        LANDMARK_TREASURE_TITLE, INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    )
    flow, _, original, _, _ = _timed_board_runtime(monkeypatch)
    runtime = flow.route.keys_runtime.treasure_runtime
    scoped = runtime.observer
    assert scoped is not original
    assert scoped.source is original.source
    assert scoped.resolver is original.resolver
    assert runtime.transition.observer is scoped
    assert any(isinstance(d, TreasureContentDetector) for d in scoped.perception.detectors)
    assert not any(isinstance(d, TreasureContentDetector) for d in original.perception.detectors)
    for detector in scoped.perception.detectors:
        name = getattr(getattr(detector, "spec", None), "name", None)
        observations = ((Observation(LANDMARK_TREASURE_TITLE, 1., ObservationSource.LOCAL_CV),)
                        if name == LANDMARK_TREASURE_TITLE else ())
        if isinstance(detector, TreasureContentDetector):
            observations = (Observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR, 1.,
                                        ObservationSource.LOCAL_CV),)
        monkeypatch.setattr(detector, "detect", lambda image, found=observations: found)
    assert is_gold_keys_content_ready(scoped.observe())
