"""Visible Tk audit with local captures; no controller start or phone access."""
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
import shutil
import sqlite3
import time
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

from PIL import ImageGrab

from bot.character_state import CharacterStateStore, DEFAULT_DB_PATH
from bot.routines import RoutineSpec, RoutineStep
from tools.gui import KritikaFarmBotGui, PROJECT_ROOT
from tools.gui_theme import AppDialog


def main():
    output = PROJECT_ROOT / 'artifacts' / ('gui_cleanup_' + uuid4().hex[:8])
    output.mkdir(parents=True)
    routine_path = output / 'routines.json'
    if (PROJECT_ROOT / 'routines.json').exists():
        shutil.copyfile(PROJECT_ROOT / 'routines.json', routine_path)
    # Review current real data on a consistent private backup, without changing the live DB.
    with sqlite3.connect(f'{DEFAULT_DB_PATH.as_uri()}?mode=ro', uri=True) as source:
        with sqlite3.connect(output / 'state.db') as target:
            source.backup(target)
    metadata = {'captures': [], 'phone_used': False, 'controller_started': False}
    callbacks = []
    root = tk.Tk()
    app = KritikaFarmBotGui(root, routine_path=routine_path,
                           character_store=CharacterStateStore(output / 'state.db'))
    root.report_callback_exception = lambda *args: callbacks.append(str(args))
    metadata['scaling'] = float(root.tk.call('tk', 'scaling'))

    def capture(name, widget=None):
        widget = root if widget is None else widget
        root.update()
        time.sleep(.2)
        root.update()
        # Tk coordinates can be DPI-virtualized on Windows; DWM gives physical bounds.
        bounds = wintypes.RECT()
        hwnd = ctypes.windll.user32.GetAncestor(widget.winfo_id(), 2)
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds))
        if result != 0:
            raise OSError('Unable to read physical window bounds for GUI capture')
        path = output / (name + '.png')
        ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom)).save(path)
        metadata['captures'].append(str(path.relative_to(PROJECT_ROOT)))

    def select(index):
        app.flow_list.selection_clear(0, 'end')
        app.flow_list.selection_set(index)
        app._load_step_settings()
        root.update()

    def theme(value):
        app.appearance_var.set(value)
        app._change_appearance()

    try:
        root.geometry('1100x760+30+30')
        root.lift()
        app.selection.draft = RoutineSpec('audit', 'GUI audit · temporary draft', (
            RoutineStep('black_market'), RoutineStep('monster_wave'),
            RoutineStep('world_boss', config={'world_boss': {'eligibility': 'DAILY_QUEST'}}),
            RoutineStep('world_boss', config={'world_boss': {'eligibility': 'CURRENT_WB_NOT_PARTICIPATED'}}),
            RoutineStep('mailbox'), RoutineStep('gold_farming')))
        app.routine_var.set(app.selection.draft.name)
        app._refresh_flow_list()
        theme('Light')
        capture('light_black_market')
        theme('Dark')
        select(2)
        capture('dark_world_boss')
        select(3)
        capture('dark_repeated_world_boss')
        select(1)
        capture('dark_monster_wave')
        root.geometry('760x560+30+30')
        capture('dark_reduced_mw_top')
        app.step_scroll.canvas.yview_moveto(1)
        capture('dark_reduced_mw_bottom')
        app.settings_tabs.select(app.routine_scroll)
        capture('dark_reduced_routine')
        # Stress the routine viewport without adding persisted config or production widgets.
        added = []
        for i in range(30):
            label = ttk.Label(app.routine_scroll.content, text=f'Scroll stress row {i + 1}')
            label.grid(row=10 + i, column=0)
            added.append(label)
        root.update()
        app.routine_scroll.canvas.yview_moveto(1)
        capture('dark_reduced_routine_scroll_stress')
        assert app.routine_scroll.canvas.yview()[1] == 1
        for label in added:
            label.destroy()
        app.routine_scroll.reset()
        root.geometry('1100x760+30+30')
        app.output_tabs.select(app.state_frame)
        app._sort_character_state('Lapiz')
        capture('dark_character_state_numeric_asc')
        app._sort_character_state('Lapiz')
        app._refresh_character_state()
        metadata['sort_after_refresh'] = [app.character_sort_column, app.character_sort_descending]
        capture('dark_character_state_numeric_desc')
        app.character_table.xview_moveto(1)
        app._sort_character_state('Resource snapshot')
        capture('dark_character_state_resources_time')
        app.character_table.xview_moveto(0)
        root.geometry('760x560+30+30')
        capture('dark_reduced_character_state')
        app.progress.character = '3 / 28 | Halo Mage'
        app.progress.flow = 'Character Data Sweep'
        app.progress.state = 'Snapshot: SAVED'
        app._sync_progress()
        app.status_var.set('Running')
        app._set_running_controls(True)
        capture('dark_reduced_sweep_progress')
        app._set_running_controls(False)
        app.status_var.set('Idle')
        root.geometry('1100x760+30+30')
        app.output_tabs.select(app.report_frame)
        capture('dark_report')
        app.output_tabs.select(app.console_frame)
        capture('dark_console')
        app.output_tabs.select(4)
        capture('dark_application')
        theme('Light')
        app.output_tabs.select(app.state_frame)
        capture('light_character_state')
        theme('Dark')
        def inspect_dialog():
            dialog = next(w for w in root.winfo_children() if isinstance(w, AppDialog))
            capture('dark_dialog', dialog)
            dialog._choose('Cancel')
        root.after(250, inspect_dialog)
        app._ask_string('Routine', 'Routine name:', initialvalue='Theme audit')
        metadata['rows'] = len(app.character_table.get_children())
        metadata['callback_errors'] = callbacks
        assert metadata['rows'] == 28 and not callbacks, callbacks
        metadata['appearance'] = app.preferences.load()
        metadata['table_before_reopen'] = {cid: app.character_table.item(cid, 'values')
                                           for cid in app.character_table.get_children()}
    finally:
        app.character_store.close()
        for callback in root.tk.call('after', 'info'):
            root.after_cancel(callback)
        root.destroy()
    root = tk.Tk()
    app = KritikaFarmBotGui(root, routine_path=routine_path,
                           character_store=CharacterStateStore(output / 'state.db'))
    try:
        app.output_tabs.select(app.state_frame)
        root.geometry('1100x760+30+30')
        capture('dark_reopened')
        after = {cid: app.character_table.item(cid, 'values') for cid in app.character_table.get_children()}
        metadata['reopen_equal'] = after == metadata.pop('table_before_reopen')
        metadata['appearance_reopened'] = app.appearance_var.get()
        assert metadata['reopen_equal'] and metadata['appearance_reopened'] == 'Dark'
    finally:
        app.character_store.close()
        for callback in root.tk.call('after', 'info'):
            root.after_cancel(callback)
        root.destroy()
    (output / 'audit.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'rows': 28, 'reopen_equal': True,
                      'appearance': 'Dark', 'scaling': metadata['scaling'], 'captures': len(metadata['captures'])}))


if __name__ == '__main__':
    main()
