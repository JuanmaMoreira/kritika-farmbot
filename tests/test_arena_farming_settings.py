from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from bot.arena_config import ArenaConfig, ArenaMode as M
from bot.arena_semantics import ArenaDifficulty as D
from bot.arena_flow import ArenaFlow
from bot.arena_farming_cycle import ArenaFarmingCycle
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.routines import RoutineEditor, RoutineStore, config_overrides
from tests.test_gui_cleanup import app, tk_root, steps, select_step, labels


@pytest.mark.parametrize('field,value', [('min_badges_for_arena', 7),
    ('min_badges_for_arena', True), ('min_sapphires_for_mw', 0),
    ('zero_win_threshold', 0), ('zero_win_threshold', 80.5), ('min_sapphires_for_mw', '100')])
def test_threshold_validation(field, value):
    with pytest.raises(ValueError): ArenaConfig(M.FARMING_CYCLE, **{field: value})


def test_routine_persistence_and_legacy_occurrences(tmp_path):
    store = RoutineStore(tmp_path/'routines.json', DEFAULT_FLOW_REGISTRY)
    editor = RoutineEditor(store); editor.create('Mixed Arena')
    editor.add('arena'); editor.add('arena'); editor.add('arena')
    editor.configure(1, {'arena': ArenaConfig(M.AUTO_REPEAT, D.NORMAL).to_dict()})
    config = ArenaConfig(M.FARMING_CYCLE, min_badges_for_arena=48, min_sapphires_for_mw=200, zero_win_threshold=96)
    editor.configure(2, {'arena': config.to_dict()}); editor.save()
    loaded = RoutineEditor(store)
    assert [config_overrides(s.config)['arena'] for s in loaded.draft.steps] == [
        ArenaConfig(), ArenaConfig(M.AUTO_REPEAT, D.NORMAL), config]
    assert 'difficulty' not in config.to_dict()
    assert ArenaConfig.from_dict({'mode': 'FARMING_CYCLE', 'difficulty': 'EASY'}).difficulty is D.HARD
    assert [d.display_name for d in DEFAULT_FLOW_REGISTRY.definitions].count('Arena') == 1
    assert 'arena_farming_cycle' not in {d.id for d in DEFAULT_FLOW_REGISTRY.definitions}


def test_gui_dynamic_visibility_per_occurrence_apply_save_and_validation(app):
    steps(app, 'arena', 'arena')
    assert 'Difficulty' in labels(app.step_scroll.content)
    app.arena_mode_var.set('Farming Cycle')
    app._render_step_settings(app.selection.draft.steps[0])
    text = labels(app.step_scroll.content)
    assert 'Difficulty' not in text and 'Minimum Brawler Badges for Arena' in text
    app.arena_min_badges_var.set('48'); app.arena_min_sapphires_var.set('200'); app.arena_zero_win_var.set('96')
    assert 'Maximum Stamina Consumption — optional' in text
    app.arena_max_stamina_var.set('500')
    app._apply_step_settings()
    select_step(app, 1)
    assert app.arena_mode_var.get() == 'Single Battle'
    assert 'Difficulty' in labels(app.step_scroll.content)
    assert 'Minimum Brawler Badges for Arena' not in labels(app.step_scroll.content)
    assert 'Maximum Stamina Consumption — optional' not in labels(app.step_scroll.content)
    select_step(app, 0)
    assert app.arena_min_badges_var.get() == '48'
    assert app.arena_max_stamina_var.get() == '500'
    errors = []; app._validation_error = errors.append
    saved = app.selection.draft.steps[0].config
    app.arena_min_badges_var.set('7'); app._apply_step_settings()
    assert errors and app.selection.draft.steps[0].config == saved
    app.arena_min_badges_var.set('not a number'); app._apply_step_settings()
    assert len(errors) == 2 and app.selection.draft.steps[0].config == saved
    app.arena_min_badges_var.set('48'); app._apply_step_settings(); app._save_routine()
    assert RoutineEditor(app.selection.store).draft.steps[0].config == saved

@pytest.mark.parametrize('value',[-1,True,60.5,'500'])
def test_optional_stamina_budget_validation(value):
    with pytest.raises(ValueError):ArenaConfig(M.FARMING_CYCLE,maximum_stamina_consumption=value)

@pytest.mark.parametrize('value',[None,0,59,60,500])
def test_optional_stamina_budget_roundtrip_and_legacy(value):
    config=ArenaConfig(M.FARMING_CYCLE,maximum_stamina_consumption=value)
    assert ArenaConfig.from_dict(config.to_dict())==config
    assert ('maximum_stamina_consumption' in config.to_dict())==(value is not None)
    assert 'maximum_stamina_consumption' not in ArenaConfig(M.SINGLE_BATTLE).to_dict()

def test_gui_empty_budget_save_reload_and_invalid_value(app):
    steps(app,'arena');app.arena_mode_var.set('Farming Cycle')
    app.arena_max_stamina_var.set('500');app._apply_step_settings()
    saved=app.selection.draft.steps[0].config
    errors=[];app._validation_error=errors.append
    app.arena_max_stamina_var.set('-1');app._apply_step_settings()
    assert errors and app.selection.draft.steps[0].config==saved
    app.arena_max_stamina_var.set('');app._apply_step_settings();app._save_routine()
    loaded=RoutineEditor(app.selection.store).draft.steps[0].config
    assert 'maximum_stamina_consumption' not in loaded['arena']
    select_step(app,0);assert app.arena_max_stamina_var.get()==''


def test_factory_uses_auto_repeat_lobby_and_existing_mw(monkeypatch):
    import bot.flow_registry as registry
    from bot.config import RuntimeConfig
    from bot.productive_runtime import ProductiveRuntime, CancellationToken
    calls = []; mw = object()
    monkeypatch.setattr(registry, '_build_monster_wave', lambda _: mw)
    import bot.stages_wiring as wiring
    manual=object()
    monkeypatch.setattr(wiring,'build_manual_stages',lambda dependencies,owner:
        manual if owner is mw else None)
    monkeypatch.setattr(ProductiveRuntime, 'build_arena_flow',
        lambda self, difficulty, **kw: calls.append((difficulty, kw)) or object())
    runtime = ProductiveRuntime(RuntimeConfig('offline', 'unused'), object(), object(),
        object(), object(), object(), object(), object(), None, CancellationToken())
    from bot.routines import RoutineStep
    step = RoutineStep('arena', config={'arena': ArenaConfig(M.FARMING_CYCLE).to_dict()})
    flow = DEFAULT_FLOW_REGISTRY.get('arena').build(runtime._step_runtime(step))
    assert flow.manual_stages is manual
    assert isinstance(flow, ArenaFarmingCycle) and flow.monster_wave is mw
    flow.arena_factory(D.HARD)
    assert calls == [(D.HARD, {'mode': M.AUTO_REPEAT, 'return_context': 'screen.lobby'})]
    assert flow.manual_stages is manual
    with pytest.raises(ValueError): ArenaFlow(None, None, None, D.HARD, mode=M.FARMING_CYCLE)
