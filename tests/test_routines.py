"""Hardware-free persistence, editor and productive runner composition contracts."""
from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from bot.config import RuntimeConfig
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import EquipmentType
from bot.flow_contracts import FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowDefinition, FlowRegistry
from bot.gui_controller import GuiRuntimeController, GuiRunStatus
from bot.gui_model import GuiExecutionRequest
from bot.monster_wave_config import MonsterWaveConfig
from bot.preconditions import MinimalPreconditionEnsurer
from bot.productive_runtime import ProductiveRuntime, CancellationToken
from bot.routines import (RoutineEditor, RoutineSpec, RoutineStep, RoutineStore,
                          config_overrides, default_routines, step_settings)
from bot.session import SessionStatus
from bot.session_report import build_session_report, ReportStatus
from test_session import Events, Flow, Rotation


@pytest.fixture
def store(tmp_path):
    return RoutineStore(tmp_path / 'routines.json', DEFAULT_FLOW_REGISTRY)


def test_missing_file_defaults_are_normal_specs_with_exact_gold_sequence(store):
    values, selected = store.load()
    assert not store.path.exists()
    assert selected == 'custom'
    assert tuple(s.flow_id for s in values[0].steps) == tuple(d.id for d in store.registry.definitions if d.id != 'gold_farming')
    assert values[1].name == 'Basic Gold Farming'
    assert tuple(s.flow_id for s in values[1].steps) == ('gold_farming',)


def test_malformed_selected_id_keeps_valid_routine(store):
    store.path.write_text(json.dumps({'version': 1, 'selected_id': [], 'routines': [
        {'id': 'r', 'name': 'Recover', 'steps': [{'flow_id': 'mailbox'}]}]}))
    assert store.load()[1] == 'r'


def test_roundtrip_order_flags_repetitions_independent_config_and_selected_id(store):
    settings = step_settings(MonsterWaveConfig(True, False),
                             EquipmentSellPolicy(frozenset({EquipmentType.RING}), True))
    routine = RoutineSpec('r', 'Mi rutina', (
        RoutineStep('monster_wave', False, settings, False),
        RoutineStep('stages_daily'), RoutineStep('monster_wave', config={}),
    ))
    store.save((routine,), 'r')
    loaded, selected = store.load()
    assert loaded == (routine,)
    assert selected == 'r'
    assert json.loads(store.path.read_text())['version'] == 1
    assert config_overrides(loaded[0].steps[0].config)['monster_wave'] == MonsterWaveConfig(True, False)
    assert config_overrides(settings)['equipment_sell'].ethereal_types == frozenset({EquipmentType.RING})
    assert loaded[0].steps[2].config == {}


def test_unknown_flow_and_config_preserved_and_skipped_without_losing_neighbors(store):
    routine = RoutineSpec('r', 'Future', (RoutineStep('mailbox'),
        RoutineStep('future_flow', config={'future_owner': {'value': 3}}), RoutineStep('mailbox')))
    store.save((routine,), 'r')
    values, _ = store.load()
    assert values == (routine,)
    assert tuple(s.flow_id for s in values[0].active_steps(store.registry)) == ('mailbox', 'mailbox')
    assert 'unknown flow' in store.warnings[0]
    store.save(values, 'r')
    assert store.load()[0] == values


@pytest.mark.parametrize('content', ['{broken', '[]', '{"version": 99, "routines": []}',
                                   '{"version": true, "routines": []}'])
def test_malformed_file_falls_back_and_original_is_backed_up_before_save(store, content):
    store.path.write_text(content)
    values, selected = store.load()
    assert values == default_routines(store.registry)
    assert store.warnings
    store.save(values, selected)
    backups = list(store.path.parent.glob('routines.json.*.bak'))
    assert len(backups) == 1
    assert backups[0].read_text() == content
    assert store.load()[0] == values


def test_bad_entries_recover_individually_and_bad_config_is_disabled_retained(store):
    store.path.write_text(json.dumps({'version': 1, 'selected_id': 'gone', 'routines': [
        {'id': 'r', 'name': 'Recover', 'steps': [
            {'flow_id': 'mailbox'}, {'flow_id': 'monster_wave', 'config': {
                'monster_wave': {'purchase_skip_tickets': 'yes'}}},
            {'flow_id': 'mailbox', 'enabled': 'false'}, {'flow_id': 'mailbox'}]},
        {'id': 'bad'}, {'id': 'r', 'name': 'Duplicate', 'steps': []},
    ]}))
    values, selected = store.load()
    assert selected == 'r'
    assert len(values) == 1
    assert [s.flow_id for s in values[0].steps] == ['mailbox', 'monster_wave', 'mailbox']
    assert not values[0].steps[1].enabled
    assert values[0].steps[1].config['monster_wave']['purchase_skip_tickets'] == 'yes'
    assert len(store.warnings) == 4


def test_new_registry_flows_available_without_reordering_saved_routine(store):
    routine = RoutineSpec('r', 'Small', (RoutineStep('mailbox'),))
    store.save((routine,), 'r')
    editor = RoutineEditor(store)
    assert editor.active_ids == ('mailbox',)
    editor.add('black_market')
    assert editor.active_ids == ('mailbox', 'black_market')


def test_editor_create_save_load_rename_duplicate_move_repeat_toggle_remove_delete(store):
    editor = RoutineEditor(store)
    editor.create('Custom farm')
    editor.add('monster_wave')
    editor.add('mailbox')
    editor.add('monster_wave')
    editor.configure(0, step_settings(MonsterWaveConfig(True), EquipmentSellPolicy()))
    editor.move_up(2)
    editor.toggle(0)
    assert editor.active_ids == ('monster_wave', 'mailbox')
    assert [o.id for o in editor.options] == [0, 1, 2]
    assert editor.options[0].display_name == editor.options[1].display_name
    editor.save()
    reopened = RoutineEditor(store)
    assert reopened.draft == editor.draft
    reopened.create('Duplicate', duplicate=True)
    reopened.configure(1, {'monster_wave': {'purchase_skip_tickets': False}})
    assert editor.draft.steps[0].config['monster_wave']['purchase_skip_tickets']
    reopened.rename('Renamed')
    reopened.remove(0)
    reopened.move_down(0)
    reopened.set_enabled(0, False)
    reopened.save()
    reopened.select(editor.selected_id)
    assert reopened.draft == editor.draft
    reopened.delete()
    assert editor.selected_id not in {r.id for r in RoutineEditor(store).routines}


def test_deleting_all_routines_survives_reopen_and_creation_is_possible(store):
    editor = RoutineEditor(store)
    while editor.draft:
        editor.delete()
    assert RoutineEditor(store).draft is None
    assert editor.options == ()
    assert editor.active_ids == ()
    with pytest.raises(ValueError, match='Create'):
        editor.add('mailbox')
    editor.create('New')
    editor.add('mailbox')
    editor.save()
    assert RoutineEditor(store).draft.name == 'New'


def make_runtime(monkeypatch, *, stage_results=None, contexts=None):
    trace, builds = [], []
    counts = {'stages_daily': 0, 'monster_wave': 0, 'mailbox': 0}
    results = list(stage_results or [])
    def definition(name):
        def factory(dependencies):
            counts[name] += 1
            builds.append((name, dependencies.config))
            result = (results.pop(0) if name == 'stages_daily' and results
                      else FlowResult(FlowStatus.COMPLETED))
            # One result per character for each independently built occurrence.
            return Flow(name, [result] * 3, trace)
        return FlowDefinition(name, name, FlowScope.PER_CHARACTER, Flow.contract, factory,
            controlled_unavailable_events=(DEFAULT_FLOW_REGISTRY.get('stages_daily').controlled_unavailable_events
                                          if name == 'stages_daily' else frozenset()))
    runtime = ProductiveRuntime(
        RuntimeConfig('offline', 'unused'), object(), object(), object(), object(), object(),
        object(), object(), Events(), CancellationToken(),
        registry=FlowRegistry(tuple(definition(n) for n in counts)))
    state = list(contexts or [])
    preconditions = MinimalPreconditionEnsurer(lambda: state.pop(0) if state else 'screen.lobby')
    monkeypatch.setattr(ProductiveRuntime, 'build_preconditions', lambda self: preconditions)
    monkeypatch.setattr(ProductiveRuntime, 'build_rotation', lambda self, count: Rotation(count, trace))
    return runtime, trace, builds


def gold(registry=DEFAULT_FLOW_REGISTRY):
    # Generic literal repetition remains independently covered after preset migration.
    return RoutineSpec('literal-gold','Literal Stages/MW',tuple(RoutineStep(f) for f in
        ('stages_daily','monster_wave','stages_daily','monster_wave')))


def test_productive_routine_exact_order_repeated_instances_and_rotation_per_character(monkeypatch):
    runtime, trace, builds = make_runtime(monkeypatch)
    result = runtime.run_routine(gold(), character_count=2)
    assert result.status is SessionStatus.COMPLETED
    assert trace == ['stages_daily.run', 'monster_wave.run', 'stages_daily.run',
                     'monster_wave.run', 'rotation.advance'] * 2
    assert [name for name, _ in builds] == ['stages_daily', 'monster_wave', 'stages_daily', 'monster_wave']
    assert result.advances_completed == 2
    assert result.flow_names == ('stages_daily', 'monster_wave', 'stages_daily', 'monster_wave')


@pytest.mark.parametrize('session', [True, False])
@pytest.mark.parametrize('second', [
    FlowResult(FlowStatus.COMPLETED),
    FlowResult(FlowStatus.COMPLETED, (FlowEvent('stages_daily.ads_exhausted'),)),
    FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.ads_unavailable'),)),
])
def test_second_stage_completed_no_work_or_unavailable_always_reaches_final_mw(monkeypatch, session, second):
    runtime, trace, _ = make_runtime(monkeypatch, stage_results=[FlowResult(FlowStatus.COMPLETED), second])
    result = runtime.run_routine(gold(), **({'character_count': 1} if session else {}))
    assert trace[:4] == ['stages_daily.run', 'monster_wave.run', 'stages_daily.run', 'monster_wave.run']
    assert len(trace) == (5 if session else 4)
    assert result.character_results[0].flow_results[2] == second if session else result.flow_results[2] == second
    if session and second.status is FlowStatus.MANUAL_RESOLUTION:
        report = build_session_report(result)
        assert report.status is ReportStatus.BUSINESS_INCOMPLETE
        assert report.advances_completed == 1


@pytest.mark.parametrize('session', [True, False])
@pytest.mark.parametrize('terminal', [
    FlowResult(FlowStatus.FAILED, error='technical failure'),
    FlowResult(FlowStatus.CANCELLED),
    FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.mw_required'),)),
    FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.preconditions_changed'),)),
    FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.ads_unavailable'),), error='unexpected'),
    FlowResult(FlowStatus.RESOURCE_BOARD_PENDING),
])
def test_failures_cancellation_and_undeclared_manual_results_stop_without_rotation(monkeypatch, session, terminal):
    runtime, trace, _ = make_runtime(monkeypatch, stage_results=[FlowResult(FlowStatus.COMPLETED), terminal])
    result = runtime.run_routine(gold(), **({'character_count': 1} if session else {}))
    assert trace == ['stages_daily.run', 'monster_wave.run', 'stages_daily.run']
    assert result.status.value != 'completed'


@pytest.mark.parametrize('session', [True, False])
def test_continue_policy_can_stop_controlled_unavailability(monkeypatch, session):
    second = FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.ads_unavailable'),))
    runtime, trace, _ = make_runtime(monkeypatch, stage_results=[FlowResult(FlowStatus.COMPLETED), second])
    routine = gold()
    steps = list(routine.steps)
    steps[2] = replace(steps[2], continue_on_unavailable=False)
    result = runtime.run_routine(replace(routine, steps=tuple(steps)), **({'character_count': 1} if session else {}))
    assert trace[-1] == 'stages_daily.run'
    assert result.status.value == 'manual_resolution'


def test_disabled_and_unknown_skipped_order_and_step_config_applied_without_global_leak(monkeypatch):
    runtime, trace, builds = make_runtime(monkeypatch)
    original = runtime.config
    configured = step_settings(MonsterWaveConfig(True), EquipmentSellPolicy(frozenset(), True))
    routine = RoutineSpec('r', 'Config', (RoutineStep('mailbox', False),
        RoutineStep('missing'), RoutineStep('monster_wave', config=configured),
        RoutineStep('monster_wave')))
    result = runtime.run_routine(routine, character_count=1)
    assert result.status is SessionStatus.COMPLETED
    assert trace == ['monster_wave.run', 'monster_wave.run', 'rotation.advance']
    assert builds[0][1].monster_wave.purchase_skip_tickets
    assert builds[0][1].equipment_sell.ethereal_enhance
    assert builds[1][1] == original
    assert runtime.config == original
    assert any(event == 'routine.step.unavailable' for event, _ in runtime.events.records)


@pytest.mark.parametrize('session', [True, False])
def test_controlled_unavailable_requires_verified_return(monkeypatch, session):
    second = FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.ads_unavailable'),))
    # First two steps each consume pre/post; third pre succeeds, third post fails.
    runtime, trace, _ = make_runtime(monkeypatch, stage_results=[FlowResult(FlowStatus.COMPLETED), second],
                                    contexts=['screen.lobby'] * 5 + ['screen.stages'])
    result = runtime.run_routine(gold(), **({'character_count': 1} if session else {}))
    assert result.status.value == 'failed'
    assert trace == ['stages_daily.run', 'monster_wave.run', 'stages_daily.run']


def test_empty_or_only_disabled_routine_rejected_without_work(monkeypatch):
    runtime, trace, _ = make_runtime(monkeypatch)
    with pytest.raises(ValueError, match='at least one'):
        runtime.run_routine(RoutineSpec('r', 'Empty', (RoutineStep('mailbox', False),)), character_count=1)
    assert trace == []


@pytest.mark.parametrize('session', [True, False])
def test_gui_controller_executes_routine_snapshot_with_existing_character_count(monkeypatch, tmp_path, session):
    runtime, trace, _ = make_runtime(monkeypatch)
    @contextmanager
    def factory(**kwargs):
        yield runtime
    request = GuiExecutionRequest.for_routine(gold(), runtime.registry,
        character_count=2 if session else None, log_dir=tmp_path)
    controller = GuiRuntimeController(registry=runtime.registry, runtime_factory=factory)
    controller.start(request)
    assert controller.wait(2)
    result = controller.drain()[-1].result
    assert result.status is GuiRunStatus.COMPLETED
    assert trace.count('monster_wave.run') == (4 if session else 2)
    assert trace.count('rotation.advance') == (2 if session else 0)
    assert request.character_count == (2 if session else 1)


@pytest.mark.parametrize('session', [True, False])
def test_invalid_config_rejected_before_any_flow_runs(monkeypatch, session):
    runtime, trace, _ = make_runtime(monkeypatch)
    routine = RoutineSpec('r', 'Bad', (RoutineStep('mailbox'),
        RoutineStep('monster_wave', config={'monster_wave': {'purchase_skip_tickets': 'yes'}})))
    with pytest.raises(ValueError):
        runtime.run_routine(routine, **({'character_count': 1} if session else {}))
    assert trace == []


@pytest.mark.parametrize('session', [True, False])
def test_unaligned_steps_rejected_without_truncating_sequence(monkeypatch, session):
    runtime, trace, _ = make_runtime(monkeypatch)
    definitions = runtime.registry.select(('mailbox', 'monster_wave'))
    with pytest.raises(ValueError, match='one routine step'):
        if session:
            runtime.run_session(definitions, character_count=1, routine_steps=(RoutineStep('mailbox'),))
        else:
            runtime.run_flows_once(definitions, routine_steps=(RoutineStep('mailbox'),))
    assert trace == []


@pytest.mark.parametrize('error', [RuntimeError('probe failed'), 'cancel'])
def test_exception_during_unavailable_return_check_cannot_be_continued(monkeypatch, error):
    from bot.runtime_observer import RuntimeWaitCancelled
    runtime, trace, _ = make_runtime(monkeypatch, stage_results=[
        FlowResult(FlowStatus.COMPLETED),
        FlowResult(FlowStatus.MANUAL_RESOLUTION, (FlowEvent('stages_daily.ads_unavailable'),))])
    preconditions = runtime.build_preconditions()
    original = preconditions.current_satisfies_any
    count = 0
    def verify(requirements):
        nonlocal count
        count += 1
        if count == 3:
            raise RuntimeWaitCancelled() if error == 'cancel' else error
        return original(requirements)
    monkeypatch.setattr(preconditions, 'current_satisfies_any', verify)
    result = runtime.run_routine(gold())
    assert result.status is (FlowStatus.CANCELLED if error == 'cancel' else FlowStatus.FAILED)
    assert trace == ['stages_daily.run', 'monster_wave.run', 'stages_daily.run']


@pytest.mark.parametrize('session', [True, False])
def test_cancellation_between_steps_and_before_start_stops_without_rotation(monkeypatch, session):
    runtime, trace, _ = make_runtime(monkeypatch)
    routine = gold()
    runtime.cancel_token.request()
    result = runtime.run_routine(routine, **({'character_count': 1} if session else {}))
    assert result.status.value == 'cancelled'
    assert trace == []
    runtime.cancel_token = CancellationToken()
    original_run = Flow.run
    def run_then_cancel(flow):
        result = original_run(flow)
        runtime.cancel_token.request()
        return result
    monkeypatch.setattr(Flow, 'run', run_then_cancel)
    result = runtime.run_routine(routine, **({'character_count': 1} if session else {}))
    assert result.status.value == 'cancelled'
    assert trace == ['stages_daily.run']


@pytest.mark.parametrize('second_unavailable', [False, True])
def test_real_stages_owner_retains_prerequisite_and_final_explicit_mw(monkeypatch, second_unavailable):
    from bot.ads_manager import AdsOutcome
    from bot.stages_daily_flow import StagesDailyFlow
    from test_stages_daily import flow, balance
    runtime, trace, _ = make_runtime(monkeypatch)
    first, first_nav, _ = flow([balance(102), balance(), balance(), balance(378)], [AdsOutcome.RETURNED],
        lambda: trace.append('mw.prerequisite') or FlowResult(FlowStatus.COMPLETED))
    if second_unavailable:
        second, _, _ = flow([balance(), balance(), balance()], [AdsOutcome.UNAVAILABLE] * 5)
    else:
        second, second_nav, _ = flow([balance(), balance()], [])
        second_nav.prepare_ad = lambda snapshot: (snapshot, 0)
    enter = first_nav.enter_target
    first_nav.enter_target = lambda: trace.append('stage.ad_path') or enter()
    occurrences = iter([first, second])
    stage_definition = FlowDefinition('stages_daily', 'Stages Ads', FlowScope.PER_CHARACTER,
        StagesDailyFlow.contract, lambda dependencies: next(occurrences),
        DEFAULT_FLOW_REGISTRY.get('stages_daily').controlled_unavailable_events)
    runtime.registry = FlowRegistry((stage_definition, runtime.registry.get('monster_wave')))
    result = runtime.run_routine(gold(), character_count=1)
    assert result.status is SessionStatus.COMPLETED
    assert trace == ['mw.prerequisite', 'stage.ad_path', 'monster_wave.run', 'monster_wave.run', 'rotation.advance']
    assert result.character_results[0].flow_results[2].events[0].kind == (
        'stages_daily.ads_unavailable' if second_unavailable else 'stages_daily.ads_exhausted')


def test_gui_callbacks_edit_positions_save_reopen_and_confirm_delete(store, monkeypatch):
    from test_gui_entrypoint import build_gui_shell, Var, Widget
    from tools import gui
    class List:
        def __init__(self):
            self.items, self.selected = [], ()
        def delete(self, *args):
            self.items, self.selected = [], ()
        def insert(self, where, item):
            self.items.append(item)
        def curselection(self):
            return self.selected
        def selection_set(self, index):
            self.selected = (index,)
        def activate(self, index):
            pass
    class Combo(Widget):
        def __init__(self):
            super().__init__()
            self.index = 0
        def current(self, index=None):
            if index is not None:
                self.index = index
            return self.index
    app = build_gui_shell(lambda: 0)
    app.selection = RoutineEditor(store)
    app.flow_list = List()
    app.routine_select = Combo()
    app.available_flow_select = Combo()
    app.routine_var = Var()
    app.purchase_skip_var, app.continue_full_var = Var(False), Var(False)
    monkeypatch.setattr(app, '_ask_string', lambda *args, **kwargs: 'New routine')
    app._new_routine()
    assert app.selection.draft.name == 'New routine'
    app.available_flow_select.index = next(i for i, d in enumerate(store.registry.definitions) if d.id == 'monster_wave')
    app._add_step()
    app.purchase_skip_var.set(True)
    app._apply_step_settings()
    app._add_step()
    app._move_up()
    assert app._selected_flow_id() == 0
    app._toggle_flow()
    assert not app.selection.draft.steps[0].enabled
    assert app.selection.draft.steps[1].config['monster_wave']['purchase_skip_tickets']
    assert app.flow_list.items[0].startswith('01.')
    assert app._save_routine()
    assert RoutineEditor(store).draft == app.selection.draft
    app._duplicate_routine()
    app._remove_step()
    assert len(app.selection.draft.steps) == 1
    assert app._save_routine()
    app._rename_routine()
    app._save_routine()
    previous = app.selection.draft.id
    monkeypatch.setattr(app, '_ask_confirmation', lambda *args, **kwargs: False)
    app._delete_routine()
    assert app.selection.draft.id == previous
    monkeypatch.setattr(app, '_ask_confirmation', lambda *args, **kwargs: True)
    app._delete_routine()
    assert previous not in {r.id for r in RoutineEditor(store).routines}


@pytest.mark.parametrize('session', [True, False])
def test_routine_events_attribute_repeated_steps_and_keep_original_positions(monkeypatch, session):
    from bot.event_log import RuntimeEventStream
    from bot.event_context import event_context
    runtime, trace, _ = make_runtime(monkeypatch)
    events = []
    runtime.events = RuntimeEventStream((events.append,))
    original = runtime.build_flow
    contexts = []
    def build(definition):
        flow = original(definition)
        run = flow.run
        def attributed_run():
            contexts.append(event_context())
            return run()
        flow.run = attributed_run
        return flow
    monkeypatch.setattr(runtime, 'build_flow', build)
    spec = RoutineSpec('audit', 'Attribution', (
        RoutineStep('mailbox', enabled=False), RoutineStep('stages_daily'),
        RoutineStep('monster_wave'), RoutineStep('stages_daily'), RoutineStep('monster_wave')))
    result = runtime.run_routine(spec, **({'character_count': 1} if session else {}))
    assert result.status.value == 'completed'
    assert [(c['step_index'], c['flow_id'], c['occurrence']) for c in contexts] == [
        (2, 'stages_daily', 1), (3, 'monster_wave', 1),
        (4, 'stages_daily', 2), (5, 'monster_wave', 2)]
    assert all(c['routine_id'] == 'audit' and c['routine_name'] == 'Attribution' for c in contexts)
    decisions = [e for e in events if e.event == 'routine.step.result']
    assert [(e.fields['step_index'], e.fields['result'], e.fields['decision']) for e in decisions] == [
        (i, 'completed', 'continue') for i in range(2, 6)]
    rotation = [e for e in events if e.event == 'rotation.started']
    assert len(rotation) == int(session)
    assert all(e.fields['step_index'] is None and e.fields['routine_id'] == 'audit' for e in rotation)


def test_occurrence_runtime_clones_share_only_recognition_backend(monkeypatch):
    runtime,_,_=make_runtime(monkeypatch)
    backend=object()
    runtime.ocr_engine=backend
    first=runtime._step_runtime(RoutineStep('monster_wave',config={'monster_wave':{'purchase_skip_tickets':True}}))
    second=runtime._step_runtime(RoutineStep('monster_wave',config={'monster_wave':{'purchase_skip_tickets':False}}))
    assert first.ocr_engine is second.ocr_engine is runtime.ocr_engine is backend
    assert first.config.monster_wave.purchase_skip_tickets
    assert not second.config.monster_wave.purchase_skip_tickets
    assert first.config is not second.config
