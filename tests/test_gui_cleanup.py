"""Ownership, projection and real Tk regressions, without device/runtime acquisition."""
from copy import deepcopy
import json
import tkinter as tk
from tkinter import ttk

import pytest

from bot.character_state import CharacterStateStore
from bot.gui_model import sorted_character_rows, CHARACTER_SORT_FIELDS
from bot.gui_preferences import GuiPreferences
from tools.gui import KritikaFarmBotGui
from tools.gui_theme import AppDialog, PALETTES


@pytest.fixture(scope='module')
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, tk_root):
    root = tk.Toplevel(tk_root)
    root.withdraw()
    errors = []
    tk_root.report_callback_exception = lambda *args: errors.append(args)
    view = KritikaFarmBotGui(root, routine_path=tmp_path / 'routines.json',
                            preferences_path=tmp_path / 'appearance.json',
                            character_store=CharacterStateStore(tmp_path / 'state.db', now=lambda: 1_000_000.))
    yield view
    view.character_store.close()
    cancel_callbacks(root)
    root.destroy()
    assert not errors


def cancel_callbacks(root):
    for callback in root.tk.call('after', 'info'):
        command = root.tk.call('after', 'info', callback)[0].split()[0]
        if command in (root._tclCommands or ()):
            root.after_cancel(callback)


def select_step(app, index):
    app.flow_list.selection_clear(0, 'end')
    app.flow_list.selection_set(index)
    app._load_step_settings()


def steps(app, *flows):
    app.selection.create('GUI regression')
    for flow in flows:
        app.selection.add(flow)
    app._refresh_routines()
    app._refresh_flow_list()


def labels(widget):
    values = []
    for child in widget.winfo_children():
        if 'text' in child.keys():
            values.append(child.cget('text'))
        values.extend(labels(child))
    return values


@pytest.mark.parametrize('flow,sections', [
    ('black_market', ()), ('mailbox', ()),
    ('world_boss', ('world_boss',)),
    ('monster_wave', ()),
    ('stages_daily', ()),
    ('gold_farming', ()),
    ('arena', ('arena',)),
])
def test_contextual_controls_and_apply_only_owned_config(app, flow, sections):
    steps(app, flow)
    assert app.visible_step_sections == sections
    text = labels(app.step_scroll.content)
    assert ('Eligibility' in text) == ('world_boss' in sections)
    assert ('Purchase SKIP tickets' in text) == ('monster_wave' in sections)
    assert 'Resource snapshot' not in text
    if not sections:
        assert 'No configurable settings for this step.' in text
        assert str(app.apply_step_button['state']) == 'disabled'
    app._apply_step_settings()
    assert set(app.selection.draft.steps[0].config) == set(sections)


def test_switch_apply_repeated_occurrences_move_duplicate_and_reopen(app):
    steps(app, 'world_boss', 'world_boss', 'monster_wave', 'black_market')
    app.wb_eligibility_var.set('CURRENT_WB_NOT_PARTICIPATED')
    select_step(app, 1)  # no silent apply of step 0
    assert app.selection.draft.steps[0].config == {}
    assert app.wb_eligibility_var.get() == 'DAILY_QUEST'
    app.wb_eligibility_var.set('GENERAL')
    app._apply_step_settings()
    select_step(app, 0)
    app.wb_eligibility_var.set('CURRENT_WB_NOT_PARTICIPATED')
    app._apply_step_settings()
    app._move_down()
    assert app._selected_flow_id() == 1
    assert app.wb_eligibility_var.get() == 'CURRENT_WB_NOT_PARTICIPATED'
    select_step(app, 2)
    app.purchase_skip_var.set(True)
    select_step(app, 3)
    app._apply_step_settings()
    assert app.selection.draft.steps[2].config == app.selection.draft.steps[3].config == {}
    app.selection.create('Duplicate', duplicate=True)
    app.selection.save()
    from bot.routines import RoutineEditor
    reopened = RoutineEditor(app.selection.store)
    assert reopened.draft.steps[0].config['world_boss']['eligibility'] == 'GENERAL'
    assert reopened.draft.steps[1].config['world_boss']['eligibility'] == 'CURRENT_WB_NOT_PARTICIPATED'


def test_arena_occurrence_form_apply_save_reload(app):
    from bot.routines import RoutineEditor
    steps(app, 'arena', 'arena')
    assert app.arena_mode_var.get()=='Single Battle' and app.arena_difficulty_var.get()=='Easy'
    app.arena_mode_var.set('Auto Repeat'); app.arena_difficulty_var.set('Hard')
    app._apply_step_settings()
    select_step(app,1)
    assert app.arena_mode_var.get()=='Single Battle' and app.arena_difficulty_var.get()=='Easy'
    app.arena_difficulty_var.set('Normal'); app._apply_step_settings()
    assert 'arena' not in RoutineEditor(app.selection.store).active_ids
    app._save_routine()
    saved=RoutineEditor(app.selection.store)
    assert [s.config['arena'] for s in saved.draft.steps]==[
        {'mode':'AUTO_REPEAT','difficulty':'HARD'}, {'mode':'SINGLE_BATTLE','difficulty':'NORMAL'}]
    select_step(app,0)
    assert app.arena_mode_var.get()=='Auto Repeat' and app.arena_difficulty_var.get()=='Hard'


def test_apply_does_not_target_new_selection_before_form_event(app):
    steps(app, 'monster_wave', 'black_market')
    app.purchase_skip_var.set(True)
    app.flow_list.selection_clear(0, 'end')
    app.flow_list.selection_set(1)
    app._apply_step_settings()
    assert all(s.config == {} for s in app.selection.draft.steps)


def test_existing_v1_overrides_are_preserved_when_form_does_not_own_them(app):
    steps(app, 'world_boss')
    app.selection.configure(0, {'monster_wave': {'purchase_skip_tickets': True}})
    select_step(app, 0)
    app.wb_eligibility_var.set('GENERAL')
    app._apply_step_settings()
    assert app.selection.draft.steps[0].config['monster_wave']['purchase_skip_tickets'] is True


def test_resource_snapshot_in_routine_scope_save_reopen_independent_of_step(app):
    steps(app, 'black_market', 'world_boss')
    assert 'Resource snapshot' in labels(app.routine_scroll.content)
    for index, mode in ((0, 'OFF'), (1, 'BEFORE_CHARACTER_ROTATION')):
        select_step(app, index)
        app.resource_snapshot_var.set(mode)
        app._set_snapshot_mode()
        app._save_routine()
        from bot.routines import RoutineEditor
        assert RoutineEditor(app.selection.store).draft.resource_snapshot_mode == mode
    assert all(s.config == {} for s in app.selection.draft.steps)


def test_reliefs_shared_draft_controls_save_duplicate_and_step_independence(app):
    steps(app, 'black_market', 'world_boss', 'monster_wave', 'stages_daily', 'gold_farming')
    assert [app.settings_tabs.tab(t, 'text') for t in app.settings_tabs.tabs()] == [
        'Step Settings', 'Routine Settings', 'Reliefs', 'Application']
    text = labels(app.relief_scroll.content)
    assert all(s in text for s in ('Socket Relief', 'Equipment Relief', 'Crafting Material Relief', 'Treasure Relief'))
    assert not any('Platinum' in s or 'Combine' in s for s in text)
    assert 'Sell Ethereal Weapon' in text and 'Sell Ethereal Enhance' in text
    app.socket_enhance_var.set(False)
    app.socket_sell_var.set(True)
    from bot.craft_semantics import CraftFamily
    for family, variable in app.craft_category_vars.items():
        variable.set(family is CraftFamily.WEAPON)
    app._apply_relief_settings()
    policy = deepcopy(app.selection.draft.relief_policy)
    for index in range(5):
        select_step(app, index)
        app._apply_step_settings()
        assert app.selection.draft.relief_policy == policy
        assert 'equipment_sell' not in app.selection.draft.steps[index].config
        assert not any('Relief' in t or 'Ethereal' in t for t in labels(app.step_scroll.content))
    app.selection.create('Copy Reliefs', duplicate=True)
    app._refresh_routines()
    assert not app.socket_enhance_var.get() and app.socket_sell_var.get()
    app._save_routine()
    from bot.routines import RoutineEditor
    assert RoutineEditor(app.selection.store).draft.relief_policy == policy


def test_settings_scroll_reaches_bottom_and_apply_remains_accessible(app):
    steps(app, 'monster_wave')
    app.root.geometry('760x560')
    app.root.deiconify()
    app.root.update()
    assert app.step_scroll.canvas.winfo_height() >= 100
    for panel in (app.step_scroll, app.routine_scroll, app.relief_scroll):
        app.settings_tabs.select(0 if panel is app.step_scroll else panel)
        if panel is not app.relief_scroll:
            for i in range(20):
                ttk.Label(panel.content, text=f'Growing settings {i}').grid(row=10 + i, column=0)
            panel.bind_content()
        app.root.update()
        assert panel.canvas.yview()[1] < 1
        panel.canvas.yview_moveto(1)
        app.root.update()
        assert panel.canvas.yview()[1] == 1
        last = panel.content.winfo_children()[-1]
        bottom = last.winfo_rooty() + last.winfo_height()
        assert bottom <= panel.canvas.winfo_rooty() + panel.canvas.winfo_height()
        last.event_generate('<MouseWheel>', delta=120)
        app.root.update()
        assert panel.canvas.yview()[1] < 1
    app.settings_tabs.select(0)
    app.root.update()
    assert app.apply_step_button.winfo_rooty() + app.apply_step_button.winfo_height() < app.root.winfo_rooty() + app.root.winfo_height()


def sort_rows(values, column):
    field = CHARACTER_SORT_FIELDS[column]
    return [dict(character_id=str(i), display_name=f'Name {i}', **({field: value} if field != 'display_name' else {}))
            | ({'display_name': value} if field == 'display_name' else {}) for i, value in enumerate(values)]


@pytest.mark.parametrize('column', ['Stage Ads', 'Lapiz', 'Dark', 'Light', 'Nature', 'K Coins'])
def test_numeric_sort_unknown_last_and_input_unchanged(column):
    rows = sort_rows([1000, None, 9, 100], column)
    original = deepcopy(rows)
    assert [r['character_id'] for r in sorted_character_rows(rows, column)] == ['2', '3', '0', '1']
    assert [r['character_id'] for r in sorted_character_rows(rows, column, True)] == ['0', '3', '2', '1']
    assert rows == original


def test_character_casefold_wb_stable_order_and_chronological_times():
    rows = sort_rows(['zulu', 'Alpha', 'bravo'], 'Character')
    assert [r['display_name'] for r in sorted_character_rows(rows)] == ['Alpha', 'bravo', 'zulu']
    assert [r['display_name'] for r in sorted_character_rows(rows, descending=True)] == ['zulu', 'bravo', 'Alpha']
    rows = sort_rows([None, 1, 0, 1], 'WB participated')
    assert [r['character_id'] for r in sorted_character_rows(rows, 'WB participated')] == ['2', '1', '3', '0']
    assert [r['character_id'] for r in sorted_character_rows(rows, 'WB participated', True)] == ['1', '3', '2', '0']
    for column in ('Resource snapshot', 'Ads status / updated'):
        rows = sort_rows([1735689600., 1704067200., None], column)  # same formatted day, different years
        assert [r['character_id'] for r in sorted_character_rows(rows, column)] == ['1', '0', '2']
        assert [r['character_id'] for r in sorted_character_rows(rows, column, True)] == ['0', '1', '2']
    rows[2]['ads_last_attempt_at'] = 1735689700.
    assert sorted_character_rows(rows, 'Ads status / updated')[-1]['character_id'] == '2'


def test_header_click_asc_desc_refresh_preserves_sort_and_sort_never_writes_db(app):
    before = app.character_store.db.total_changes
    for column in ('Character', 'Stage Ads', 'WB participated', 'Lapiz', 'Resource snapshot'):
        app.root.tk.call(app.character_table.heading(column, 'command'))
        assert not app.character_sort_descending
        app.root.tk.call(app.character_table.heading(column, 'command'))
        assert app.character_sort_descending
        expected = [r['character_id'] for r in sorted_character_rows(app._character_rows, column, True)]
        assert list(app.character_table.get_children()) == expected
    assert app.character_store.db.total_changes == before
    app._refresh_character_state()
    assert app.character_sort_column == 'Resource snapshot'
    assert app.character_sort_descending
    assert len(app.character_table.get_children()) == 28
    assert list(app.character_table.get_children()) == expected
    assert 'All 28' in app.sweep_button['text']


def test_treeview_column_values_match_headers_and_sort_projection(app):
    app.character_store.ads('monk', 'OBSERVED', observed_count=1)
    app.character_store.wb('monk', True, source='GUI_TEST')
    resources = dict(lapiz=9, dark_essence=100, light_essence=1000, nature_essence=12, k_coins=345)
    app.character_store.resources('monk', resources)
    app._refresh_character_state()
    assert app.character_table.set('monk', 'Stage Ads') == '1'
    assert app.character_table.set('monk', 'WB participated') == 'YES'
    for column, field in CHARACTER_SORT_FIELDS.items():
        if field in resources:
            assert app.character_table.set('monk', column) == str(resources[field])
            app._sort_character_state(column)
            assert app.character_table.get_children()[0] == 'monk'


def test_dynamic_dark_light_styles_persistence_and_separate_storage(app):
    before_routine = app.selection.store.path.read_bytes()
    before_db = app.character_store.db.total_changes
    app.controller.start = lambda _: pytest.fail('Theme must not invoke runtime')
    for appearance in ('Dark', 'Light', 'Dark'):
        app.appearance_var.set(appearance)
        app._change_appearance()
        palette = PALETTES[appearance]
        assert app.root['background'] == palette['background']
        assert app.theme.style.lookup('Treeview', 'fieldbackground') == palette['surface']
        assert app.console['background'] == app.report_text['background'] == palette['surface']
        assert app.theme.style.lookup('TCombobox', 'fieldbackground', ('readonly',)) == palette['surface']
        assert app.theme.style.lookup('Treeview', 'background', ('selected',)) == palette['selection']
        assert GuiPreferences(app.preferences.path).load() == appearance
    assert app.selection.store.path.read_bytes() == before_routine
    assert app.character_store.db.total_changes == before_db
    payload = json.loads(app.preferences.path.read_text())
    assert payload == {'appearance': 'Dark'}
    second_root = tk.Toplevel(app.root)
    second_root.withdraw()
    try:
        reopened = KritikaFarmBotGui(second_root, routine_path=app.selection.store.path,
                                   preferences_path=app.preferences.path,
                                   character_store=CharacterStateStore(app.character_store.path))
        assert reopened.appearance_var.get() == 'Dark'
        assert reopened.theme.tokens == PALETTES['Dark']
        reopened.character_store.close()
        cancel_callbacks(second_root)
    finally:
        second_root.destroy()


def test_themed_dialog_entry_and_confirmation(app):
    app.appearance_var.set('Dark')
    app._change_appearance()
    def close_dialog():
        dialog = next(w for w in app.root.winfo_children() if isinstance(w, AppDialog))
        assert dialog['background'] == PALETTES['Dark']['background']
        if hasattr(dialog, 'entry'):
            dialog.entry.delete(0, 'end')
            dialog.entry.insert(0, 'Renamed')
            dialog._choose('OK')
        else:
            dialog._choose('No')
    app.root.after(50, close_dialog)
    assert app._ask_string('Routine', 'Name', initialvalue='Old') == 'Renamed'
    app.root.after(50, close_dialog)
    assert app._ask_confirmation('Delete', 'Delete routine?', cancel=True) is False


@pytest.mark.parametrize('mode', ['OFF', 'BEFORE_CHARACTER_ROTATION'])
def test_normal_routine_from_gui_keeps_snapshot_hook_before_each_rotation(app, monkeypatch, mode):
    """Exercise GUI request → run_routine → production build_rotation collector → SQLite."""
    from types import SimpleNamespace
    from bot.character_state import character_state_scope, establish_character_state
    from bot.event_log import RuntimeEventStream
    from bot.productive_runtime import ProductiveRuntime, CancellationToken
    from bot.routines import RoutineSpec, RoutineStep
    import bot.productive_runtime as productive

    steps(app, 'mailbox')
    app.resource_snapshot_var.set(mode)
    app._set_snapshot_mode()
    request = app._execution_request(2)
    trace = []
    snapshot = object()
    values = dict(lapiz=9, dark_essence=100, light_essence=1000, nature_essence=12, k_coins=345)
    reader = SimpleNamespace(read=lambda qm, **kwargs: (trace.append(('snapshot', qm)), values)[1])
    monkeypatch.setattr(productive, 'QuickMenuResourceReader', lambda *args, **kwargs: reader)
    monkeypatch.setattr(productive, 'StandardRotation', lambda *args, **kwargs: SimpleNamespace(**kwargs))
    runtime = ProductiveRuntime(config=object(), observer=object(), actions=object(), facts=object(),
        auto_battle=object(), socket_relief=object(), equipment_combine_relief=object(),
        pet_summon_space_relief=object(), events=RuntimeEventStream(), cancel_token=CancellationToken(),
        character_store=app.character_store, ocr_engine=object(), resource_snapshot_mode='OFF')
    monkeypatch.setattr(runtime, 'build_verified_transition', lambda: object())
    monkeypatch.setattr(productive, 'scoped_observer_for', lambda *args, **kwargs: object())
    monkeypatch.setattr(productive, 'scoped_transition_for', lambda *args, **kwargs: object())
    def session(definitions, *, character_count, **kwargs):
        assert runtime.resource_snapshot_mode == mode
        rotation = runtime.build_rotation(character_count)
        for cid in ('monk', 'halo_mage'):
            with character_state_scope():
                establish_character_state(app.character_store, cid)
                trace.append(('QM', snapshot))
                rotation.quick_menu_ready(snapshot, origin='screen.lobby')
                trace.append(('Select', snapshot))
        return 'completed'
    monkeypatch.setattr(runtime, 'run_session', session)
    assert runtime.run_routine(request.routine, character_count=request.character_count) == 'completed'
    assert runtime.resource_snapshot_mode == 'OFF'
    expected = [('QM', snapshot), ('snapshot', snapshot), ('Select', snapshot)] if mode != 'OFF' else [('QM', snapshot), ('Select', snapshot)]
    assert trace == expected * 2
    rows = {r['character_id']: r for r in app.character_store.rows()}
    for cid in ('monk', 'halo_mage'):
        for field, value in values.items():
            assert rows[cid][field] == (value if mode != 'OFF' else None)


def test_preferences_invalid_file_falls_back_light(tmp_path):
    path = tmp_path / 'preferences.json'
    preferences = GuiPreferences(path)
    for raw in ('{broken', '[]', '{}', '{"appearance":"SYSTEM"}'):
        path.write_text(raw)
        assert preferences.load() == 'Light'



def test_change_meteorites_is_routine_only_apply_save_reopen_duplicate(app):
    from bot.routines import RoutineEditor
    steps(app,'mailbox','black_market')
    assert not app.change_meteorites_var.get() and not app.selection.draft.change_meteorites
    assert 'Change Meteorites' in labels(app.routine_scroll.content)
    assert 'Change Meteorites' not in labels(app.step_scroll.content)
    assert 'Change Meteorites' not in labels(app.relief_scroll.content)
    app.change_meteorites_var.set(True);app._show_meteorites_notice()
    assert app.meteorites_notice.winfo_manager()=='grid'
    assert 'Antes de iniciar la sesión, desequipá el set' in app.meteorites_notice['text']
    assert not app.selection.draft.change_meteorites
    app._apply_routine_settings()
    assert app.selection.draft.change_meteorites
    persisted=RoutineEditor(app.selection.store)
    assert not persisted.draft.change_meteorites
    app.selection.save()
    assert RoutineEditor(app.selection.store).draft.change_meteorites
    app.selection.create('Copy meteorites',duplicate=True)
    app._refresh_routines()
    assert app.change_meteorites_var.get() and app.selection.draft.change_meteorites
    app.selection.save()
    assert RoutineEditor(app.selection.store).draft.change_meteorites
    app.change_meteorites_var.set(False);app._show_meteorites_notice()
    assert app.meteorites_notice.winfo_manager()=='' and app.selection.draft.change_meteorites
    app._apply_routine_settings();app.selection.save()
    assert not RoutineEditor(app.selection.store).draft.change_meteorites
    assert all('change_meteorites' not in step.config for step in app.selection.draft.steps)
