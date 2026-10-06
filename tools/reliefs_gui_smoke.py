"""Visible real Tk audit of routine Reliefs; no runtime or phone inputs."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import shutil
import time
import tkinter as tk
from uuid import uuid4

from PIL import ImageGrab

from bot.character_state import CharacterStateStore
from tools.gui import KritikaFarmBotGui


def main():
    output = Path('artifacts') / ('reliefs_gui_' + uuid4().hex[:8])
    output.mkdir()
    shutil.copyfile('routines.json', output / 'routines.json')
    captures, errors = [], []
    root = tk.Tk()
    root.report_callback_exception = lambda *args: errors.append(str(args))
    app = KritikaFarmBotGui(root, routine_path=output / 'routines.json',
        preferences_path=output / 'preferences.json', character_store=CharacterStateStore(output / 'state.db'))

    def capture(name):
        root.update()
        time.sleep(.2)
        root.update()
        bounds = wintypes.RECT()
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds)):
            raise OSError('GUI window bounds unavailable')
        path = output / (name + '.png')
        ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom)).save(path)
        captures.append(str(path.resolve()))

    try:
        root.geometry('1100x760+30+30')
        root.lift()
        for theme in ('Light', 'Dark'):
            app.appearance_var.set(theme)
            app._change_appearance()
            app.settings_tabs.select(app.relief_scroll)
            app.relief_scroll.reset()
            capture(theme.lower() + '_reliefs_top')
            root.geometry('760x560+30+30')
            capture(theme.lower() + '_reduced_top')
            app.relief_scroll.canvas.yview_moveto(1)
            capture(theme.lower() + '_reduced_bottom')
            assert app.relief_scroll.canvas.yview()[1] == 1
            root.geometry('1100x760+30+30')
        for index, step in enumerate(app.selection.draft.steps):
            app.settings_tabs.select(0)
            app.flow_list.selection_clear(0, 'end')
            app.flow_list.selection_set(index)
            app._load_step_settings()
            capture('step_' + step.flow_id)
            assert 'equipment_sell' not in app.visible_step_sections
        app.settings_tabs.select(app.routine_scroll)
        capture('routine_settings')
        app.settings_tabs.select(app.application_scroll)
        capture('application')
        before = app.selection.draft
        app._save_routine()
        from bot.routines import RoutineEditor
        assert RoutineEditor(app.selection.store).draft == before
        assert not errors, errors
        payload = {'captures': captures, 'callback_errors': errors, 'save_reopen_equal': True,
                   'tabs': [app.settings_tabs.tab(t, 'text') for t in app.settings_tabs.tabs()],
                   'relief_policy': before.relief_policy, 'runtime_started': False, 'phone_inputs': 0}
        (output / 'audit.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(output.resolve()), 'tabs': payload['tabs'], 'save_reopen_equal': True}))
    finally:
        app.character_store.close()
        for callback in root.tk.call('after', 'info'):
            root.after_cancel(callback)
        root.destroy()


if __name__ == '__main__':
    main()
