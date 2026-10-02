"""MW shares the session zone without installing Eligibility."""
from types import SimpleNamespace
from unittest.mock import Mock

from bot.flow_contracts import FlowContract, FlowResult, FlowScope, FlowStatus
from bot.component_contracts import ComponentRequirement
from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_productive import ProductiveMonsterWaveFlow
from bot.prepared_activity import PreparedActivity
from bot.world_boss_flow import WorldBossFlow
from test_productive_runtime import _runtime, Events
from test_session import Rotation
import bot.productive_runtime as productive


def _zone():
    return SimpleNamespace(
        entry_requirement=ComponentRequirement.exact_state(SCREEN_LOBBY),
        hub_requirement=ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
        enter=Mock(),
        leave=Mock(),
    )


def _productive(zone):
    flow = ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow)
    flow.zone = zone
    return flow


def _bare(zone):
    flow = MonsterWaveFlow.__new__(MonsterWaveFlow)
    flow.activity = Mock()
    flow.activity.run = Mock()
    flow.zone = zone
    return flow


def _world_boss(zone):
    flow = WorldBossFlow.__new__(WorldBossFlow)
    flow.zone = zone
    return flow


def _other():
    return SimpleNamespace(
        name="mailbox",
        scope=FlowScope.PER_CHARACTER,
        contract=FlowContract(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            (ComponentRequirement.exact_state(SCREEN_LOBBY),),
        ),
        run=Mock(return_value=FlowResult(FlowStatus.COMPLETED)),
    )


def _capture_session(monkeypatch, runtime, flows):
    captured = {}
    monkeypatch.setattr(runtime, "build_flows", lambda definitions: flows)
    monkeypatch.setattr(runtime, "build_rotation", lambda count: Rotation(count, []))
    monkeypatch.setattr(
        runtime, "build_world_boss_daily_eligibility",
        lambda: SimpleNamespace(evaluate=lambda: None),
    )

    def fake_runner(plan, **kwargs):
        captured["plan"] = plan
        runner = Mock()
        runner.run.return_value = SimpleNamespace(status="captured")
        return runner

    monkeypatch.setattr(productive, "SessionRunner", fake_runner)
    result = runtime.run_session((), character_count=1)
    assert result.status == "captured"
    return captured["plan"]


def test_productive_monster_wave_prepared_with_shared_zone_without_eligibility(monkeypatch):
    zone = _zone()
    flow = _productive(zone)
    flow._run_activity_l1 = Mock(return_value=FlowResult(FlowStatus.COMPLETED))
    runtime = _runtime(SimpleNamespace(), Events())
    plan = _capture_session(monkeypatch, runtime, (flow,))
    assert len(plan.flows) == 1
    prepared = plan.flows[0]
    assert isinstance(prepared, PreparedActivity)
    assert prepared.name == "monster_wave"
    assert prepared.zone is zone
    assert plan.eligibility == (None,)
    prepared.run()
    flow._run_activity_l1.assert_called_once_with()


def test_bare_monster_wave_keeps_same_binding(monkeypatch):
    zone = _zone()
    flow = _bare(zone)
    runtime = _runtime(SimpleNamespace(), Events())
    plan = _capture_session(monkeypatch, runtime, (flow,))
    prepared = plan.flows[0]
    assert isinstance(prepared, PreparedActivity)
    assert prepared.zone is zone
    prepared.run()
    flow.activity.run.assert_called_once()
    _, kwargs = flow.activity.run.call_args
    assert kwargs == {"yield_resource_board": False}
    assert plan.eligibility == (None,)


def test_world_boss_and_other_flows_unchanged_with_productive_zone_sharing(monkeypatch):
    mw_zone = _zone()
    wb_zone = _zone()
    productive = _productive(mw_zone)
    wb = _world_boss(wb_zone)
    other = _other()
    runtime = _runtime(SimpleNamespace(), Events())
    plan = _capture_session(monkeypatch, runtime, (wb, productive, other))
    # La primera zona encontrada (WB) se comparte con el MW productivo.
    assert isinstance(plan.flows[0], PreparedActivity)
    assert isinstance(plan.flows[1], PreparedActivity)
    assert plan.flows[0].zone is wb_zone
    assert plan.flows[1].zone is wb_zone
    assert plan.flows[1].name == "monster_wave"
    # Otros flows pasan sin envolver.
    assert plan.flows[2] is other
    assert plan.eligibility[0] is not None
    assert plan.eligibility[1:] == (None, None)


def test_productive_prepared_activity_keeps_zone_identity_for_runner_ordering():
    zone = _zone()
    flow = _productive(zone)
    prepared = flow.prepared(zone)
    assert isinstance(prepared, PreparedActivity)
    assert prepared.zone is zone
    # Mismo contrato que bare: precondition de hub, por lo que SessionRunner
    # hace enter de zona antes del precheck de Sapphires.
    bare = _bare(zone)
    bare_prepared = bare.prepared(zone)
    assert type(prepared.contract.precondition) is type(bare_prepared.contract.precondition)
