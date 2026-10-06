"""Operational Tkinter frontend for the productive Kritika FarmBot runtime."""

from __future__ import annotations

import argparse
from datetime import datetime
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from bot.config import DEFAULT_CHARACTER_COUNT
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import CONFIGURABLE_EQUIPMENT_TYPES
from bot.event_log import format_runtime_event
from bot.gui_controller import (
    GuiExecutionResult,
    GuiMessageKind,
    GuiRunStatus,
    GuiRuntimeController,
)
from bot.gui_model import (
    FlowSelectionModel,
    GuiExecutionRequest,
    GuiProgress,
    GuiRunMode,
    SessionElapsedTimer,
    event_visible,
    STEP_CONFIG_SECTIONS, CHARACTER_SORT_FIELDS, sorted_character_rows,
)
from bot.routines import RoutineEditor, RoutineStore, config_overrides, step_settings
from bot.gui_preferences import GuiPreferences
from tools.gui_theme import GuiTheme, ScrollableSettings, AppDialog
from bot.character_state import CharacterStateStore, stamp
from bot.character_data import ResourceSnapshotMode
from bot.world_boss_state import WorldBossEligibilityMode
from bot.monster_wave_config import MonsterWaveConfig
from bot.relief_policy import ReliefPolicy, SocketReliefPolicy
from bot.craft_semantics import CraftFamily
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.productive_runtime import PROJECT_ROOT
from bot.gui_evidence import locate_evidence, report_evidence_refs
from bot.session_report import render_session_report


POLL_INTERVAL_MS = 50
SESSION_TIMER_INTERVAL_MS = 1000
MAX_VISIBLE_CONSOLE_LINES = 5000


class KritikaFarmBotGui:
    """Tk widgets only; product execution remains in GuiRuntimeController."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
        routine_path: Path = PROJECT_ROOT / "routines.json",
        preferences_path: Path = PROJECT_ROOT / "runtime" / "gui_preferences.json",
        character_store: CharacterStateStore | None = None,
    ) -> None:
        self.root = root
        self.character_store = character_store if character_store is not None else CharacterStateStore()
        self.preferences = GuiPreferences(preferences_path)
        self.theme = GuiTheme(root)
        self.appearance_var = tk.StringVar(root, value=self.preferences.load())
        self.character_sort_column = None
        self.character_sort_descending = False
        self._character_rows = []
        self._settings_step_index = None
        self._character_refresh_after = None
        self.dotenv_path = Path(dotenv_path)
        self.log_dir = Path(log_dir)
        self.selection = RoutineEditor(RoutineStore(routine_path, DEFAULT_FLOW_REGISTRY))
        if not self.selection.store.path.exists():
            try:
                self.selection.save()
            except OSError as error:
                self.selection.store.warnings.append(f"Cannot initialize routine file: {error}")
        self.controller = GuiRuntimeController(registry=self.selection.registry)
        self.progress = GuiProgress()
        self.session_timer = SessionElapsedTimer()
        self._active_mode: GuiRunMode | None = None
        self._debug_for_run = False
        self._close_when_idle = False

        root.title("Kritika FarmBot")
        root.geometry("1100x760")
        root.minsize(760, 560)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.routine_var = tk.StringVar()
        self.wb_eligibility_var = tk.StringVar(value=WorldBossEligibilityMode.DAILY_QUEST.value)
        self.resource_snapshot_var = tk.StringVar(value=ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value)
        self.available_flow_var = tk.StringVar()
        self.purchase_skip_var = tk.BooleanVar(value=False)
        self.continue_full_var = tk.BooleanVar(value=False)
        self.characters_var = tk.StringVar(value=str(DEFAULT_CHARACTER_COUNT))
        self.debug_var = tk.BooleanVar(value=False)
        default_sell = EquipmentSellPolicy()
        self.ethereal_type_vars = {
            t: tk.BooleanVar(value=t in default_sell.ethereal_types)
            for t in sorted(CONFIGURABLE_EQUIPMENT_TYPES, key=lambda t: t.value)
        }
        self.ethereal_enhance_var = tk.BooleanVar(value=default_sell.ethereal_enhance)
        self.socket_enhance_var = tk.BooleanVar(value=True)
        self.socket_sell_var = tk.BooleanVar(value=True)
        self.craft_category_vars = {f: tk.BooleanVar(value=True) for f in CraftFamily}
        self.treasure_gold_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=GuiRunStatus.IDLE.value)
        self.character_var = tk.StringVar(value="-")
        self.flow_var = tk.StringVar(value="-")
        self.state_var = tk.StringVar(value="-")
        self.result_var = tk.StringVar(value="Ready")
        self.log_var = tk.StringVar(value="Log: -")
        self.session_elapsed_var = tk.StringVar(value=self.session_timer.text)
        self.evidence_var = tk.StringVar(value="")
        self.evidence_status_var = tk.StringVar(value="")

        self.theme.apply(self.appearance_var.get())
        self._build_layout()
        self.theme.apply(self.appearance_var.get())
        self._refresh_routines()
        self._refresh_flow_list()
        if self.selection.store.warnings:
            self.result_var.set("; ".join(self.selection.store.warnings))
        self._set_running_controls(False)
        self.root.after(POLL_INTERVAL_MS, self._drain_worker)
        self.root.after(SESSION_TIMER_INTERVAL_MS, self._refresh_session_timer)
        self._refresh_character_state()

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        run = ttk.Frame(outer, padding=(0, 4))
        run.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(run, text="Run routine · Characters").grid(row=0, column=0, sticky="w")
        self.characters = ttk.Spinbox(run, from_=1, to=999, width=5, textvariable=self.characters_var)
        self.characters.grid(row=0, column=1, padx=6)
        self.debug_check = ttk.Checkbutton(run, text="Debug", variable=self.debug_var)
        self.debug_check.grid(row=0, column=2, padx=6)
        self.run_flow_button = ttk.Button(run, text="Run Selected Flows", command=self._run_selected_flows)
        self.run_flow_button.grid(row=0, column=3, padx=4)
        self.run_session_button = ttk.Button(run, text="Run Session", command=self._run_session)
        self.run_session_button.grid(row=0, column=4, padx=4)
        self.stop_button = ttk.Button(run, text="Stop Safely", command=self._stop_safely)
        self.stop_button.grid(row=0, column=5, padx=4)

        self.output_tabs = ttk.Notebook(outer)
        self.output_tabs.grid(row=2, column=0, sticky="nsew")
        self.editor_frame = ttk.Frame(self.output_tabs, padding=8)
        self.output_tabs.add(self.editor_frame, text="Routine Editor")
        self.editor_frame.columnconfigure(0, weight=1)
        self.editor_frame.columnconfigure(1, weight=2)
        self.editor_frame.rowconfigure(1, weight=1)
        self.routine_controls = []
        routines = ttk.Frame(self.editor_frame)
        routines.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        routines.columnconfigure(0, weight=1)
        self.routine_select = ttk.Combobox(routines, textvariable=self.routine_var, state="readonly")
        self.routine_select.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.routine_select.bind("<<ComboboxSelected>>", self._select_routine)
        for column, (label, command) in enumerate((
                ("New", self._new_routine), ("Duplicate", self._duplicate_routine),
                ("Rename", self._rename_routine), ("Save Routine", self._save_routine),
                ("Delete", self._delete_routine)), start=1):
            button = ttk.Button(routines, text=label, command=command)
            button.grid(row=0, column=column, padx=2)
            self.routine_controls.append(button)

        flows = ttk.LabelFrame(self.editor_frame, text="Steps — execution order", padding=8)
        flows.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        flows.columnconfigure(0, weight=1)
        flows.rowconfigure(0, weight=1)
        self.flow_list = tk.Listbox(flows, height=5, width=24, exportselection=False)
        self.flow_list.grid(row=0, column=0, sticky="nsew")
        self.flow_list.bind("<<ListboxSelect>>", lambda _: self._load_step_settings())
        self.flow_list.bind("<Double-Button-1>", lambda _: self._toggle_flow())
        self.flow_list.bind("<space>", lambda _: self._toggle_flow())
        bar = ttk.Scrollbar(flows, orient='vertical', command=self.flow_list.yview)
        bar.grid(row=0, column=1, sticky='ns')
        self.flow_list.configure(yscrollcommand=bar.set)
        xbar = ttk.Scrollbar(flows, orient='horizontal', command=self.flow_list.xview)
        xbar.grid(row=1, column=0, sticky='ew')
        self.flow_list.configure(xscrollcommand=xbar.set)
        step_actions = ttk.Frame(flows)
        step_actions.grid(row=2, column=0, columnspan=2, sticky='ew', pady=6)
        self.toggle_button = ttk.Button(step_actions, text="Enable / Disable", command=self._toggle_flow)
        self.up_button = ttk.Button(step_actions, text="↑ Up", command=self._move_up)
        self.down_button = ttk.Button(step_actions, text="↓ Down", command=self._move_down)
        for column, button in enumerate((self.toggle_button, self.up_button, self.down_button)):
            button.grid(row=0, column=column, padx=2, sticky='ew')
            step_actions.columnconfigure(column, weight=1)
        remove = ttk.Button(step_actions, text="Remove", command=self._remove_step)
        remove.grid(row=1, column=0, columnspan=3, sticky='ew', padx=2, pady=(4, 0))
        self.routine_controls.append(remove)
        available = ttk.Frame(flows)
        available.grid(row=3, column=0, columnspan=2, sticky='ew')
        available.columnconfigure(0, weight=1)
        self.available_flow_select = ttk.Combobox(available, textvariable=self.available_flow_var,
            values=tuple(d.display_name for d in self.selection.registry.definitions), state="readonly", width=18)
        self.available_flow_select.grid(row=0, column=0, sticky="ew")
        self.available_flow_select.current(0)
        add = ttk.Button(available, text="Add flow", command=self._add_step)
        add.grid(row=0, column=1, sticky='ew', padx=(4, 0))
        self.routine_controls.append(add)

        settings = ttk.Notebook(self.editor_frame)
        settings.grid(row=1, column=1, sticky='nsew')
        step_frame = ttk.Frame(settings)
        settings.add(step_frame, text='Step Settings')
        step_frame.columnconfigure(0, weight=1)
        step_frame.rowconfigure(1, weight=1)
        self.step_heading_var = tk.StringVar()
        ttk.Label(step_frame, textvariable=self.step_heading_var, font=('Segoe UI', 11, 'bold'),
                  padding=8).grid(row=0, column=0, sticky='ew')
        self.step_scroll = ScrollableSettings(step_frame)
        self.step_scroll.grid(row=1, column=0, sticky='nsew')
        self.apply_step_button = ttk.Button(step_frame, text='Apply to selected step', command=self._apply_step_settings)
        self.apply_step_button.grid(row=2, column=0, sticky='ew', padx=8, pady=(6, 0))
        ttk.Label(step_frame, text='Apply → routine draft. Save Routine → disk.\nSwitching steps discards unapplied edits.',
                  style='Muted.TLabel', padding=8).grid(row=3, column=0, sticky='ew')

        self.routine_scroll = ScrollableSettings(settings)
        settings.add(self.routine_scroll, text='Routine Settings')
        content = self.routine_scroll.content
        ttk.Label(content, text='Whole routine / each character', font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(content, text='Resource snapshot').grid(row=1, column=0, sticky='w', pady=(16, 4))
        self.resource_select = ttk.Combobox(content, textvariable=self.resource_snapshot_var,
            values=tuple(m.value for m in ResourceSnapshotMode), state='readonly', width=30)
        self.resource_select.grid(row=2, column=0, sticky='ew')
        self.resource_select.bind('<<ComboboxSelected>>', self._set_snapshot_mode)
        ttk.Label(content, text='BEFORE_CHARACTER_ROTATION captures Lapiz, Dark, Light, Nature and K Coins '
                  'from Rotation’s Quick Menu before Character Select.\n\nChanging this setting updates the routine draft. '
                  'Use Save Routine to persist.', wraplength=340, style='Muted.TLabel').grid(row=3, column=0, sticky='ew', pady=12)
        self.routine_scroll.bind_content()
        self.routine_controls.append(self.resource_select)
        self._build_relief_settings(settings)
        self.settings_tabs = settings

        state_frame = ttk.Frame(self.output_tabs, padding=6)
        self.output_tabs.add(state_frame, text='Character State')
        self.state_frame = state_frame
        state_frame.rowconfigure(1, weight=1)
        state_frame.columnconfigure(0, weight=1)
        self.reset_clock_var = tk.StringVar()
        state_header = ttk.Frame(state_frame)
        state_header.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(state_header, textvariable=self.reset_clock_var).pack(side='left')
        self.sweep_button = ttk.Button(state_header, text='Character Data Sweep — All 28', command=self._run_character_data_sweep)
        self.sweep_button.pack(side='right', padx=8, pady=4)
        columns = tuple(CHARACTER_SORT_FIELDS)
        self.character_table = ttk.Treeview(state_frame, columns=columns, show='headings', height=18)
        for column in columns:
            self.character_table.heading(column, text=column, command=lambda c=column: self._sort_character_state(c))
            width = 165 if column == 'Character' else 180 if column in ('Ads status / updated', 'Resource snapshot') else 135
            self.character_table.column(column, width=width, stretch=False)
        self.character_table.grid(row=1, column=0, sticky='nsew')
        xbar = ttk.Scrollbar(state_frame, orient='horizontal', command=self.character_table.xview)
        xbar.grid(row=2, column=0, sticky='ew')
        ybar = ttk.Scrollbar(state_frame, orient='vertical', command=self.character_table.yview)
        ybar.grid(row=1, column=1, sticky='ns')
        self.character_table.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)

        self.report_frame = ttk.Frame(self.output_tabs, padding=8)
        self.output_tabs.add(self.report_frame, text="Session Report")
        self.report_frame.columnconfigure(0, weight=1)
        self.report_frame.rowconfigure(0, weight=1)
        self.report_text = ScrolledText(self.report_frame, wrap="word", height=8, state="disabled")
        self._theme_text_scrollbar(self.report_text)
        self.report_text.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.evidence_select = ttk.Combobox(self.report_frame, textvariable=self.evidence_var, state="readonly")
        self.evidence_select.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        self.evidence_button = ttk.Button(self.report_frame, text="Locate evidence", command=self._locate_evidence, state="disabled")
        self.evidence_button.grid(row=1, column=1, padx=(8, 0), pady=(7, 0))
        ttk.Label(self.report_frame, textvariable=self.evidence_status_var).grid(row=2, column=0, columnspan=2, sticky="w")
        self.console_frame = ttk.Frame(self.output_tabs, padding=8)
        self.output_tabs.add(self.console_frame, text="Debug Console")
        self.console_frame.columnconfigure(0, weight=1)
        self.console_frame.rowconfigure(0, weight=1)
        self.console = ScrolledText(self.console_frame, wrap="none", height=8, font=("Consolas", 9), state="disabled")
        self._theme_text_scrollbar(self.console)
        self.console.grid(row=0, column=0, columnspan=3, sticky="nsew")
        for column, (text, command) in enumerate((('Clear', self._clear_console),
                ('Copy selected', self._copy_selected), ('Copy all', self._copy_all))):
            ttk.Button(self.console_frame, text=text, command=command).grid(row=1, column=column, pady=7)

        self.application_scroll = ScrollableSettings(self.settings_tabs)
        self.settings_tabs.add(self.application_scroll, text='Application')
        application = self.application_scroll.content
        ttk.Label(application, text='Application Settings', font=('Segoe UI', 12, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(application, text='Appearance').grid(row=1, column=0, sticky='w', pady=(18, 4))
        appearance = ttk.Combobox(application, textvariable=self.appearance_var, values=('Light', 'Dark'), state='readonly', width=18)
        appearance.grid(row=2, column=0, sticky='w')
        appearance.bind('<<ComboboxSelected>>', self._change_appearance)
        ttk.Label(application, text='Applied immediately and remembered for the application.', style='Muted.TLabel').grid(row=3, column=0, pady=12)

        self.application_scroll.bind_content()

        status = ttk.LabelFrame(outer, text="Status / Progress — active task", padding=6)
        status.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for column in range(5):
            status.columnconfigure(column, weight=1)
        for column, (label, variable) in enumerate((("Status", self.status_var), ('Character', self.character_var),
                ('Flow', self.flow_var), ('State', self.state_var), ('Session elapsed', self.session_elapsed_var))):
            self._status_pair(status, column, label, variable)
        ttk.Label(status, text="Result:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        result = ttk.Label(status, textvariable=self.result_var, wraplength=600)
        result.grid(row=2, column=1, columnspan=4, sticky='ew', pady=(6, 0))
        ttk.Label(status, textvariable=self.log_var, wraplength=700, style='Muted.TLabel').grid(row=3, column=0, columnspan=5, sticky='ew')
        status.bind('<Configure>', lambda e: result.configure(wraplength=max(180, e.width - 140)))
        self.output_tabs.select(self.editor_frame)
        self.sell_policy_checks = []
        self.step_controls = []

    @staticmethod
    def _theme_text_scrollbar(widget):
        # Native Tk scrollbars on Windows ignore palette colors; use the ttk owner.
        widget.vbar.destroy()
        widget.vbar = ttk.Scrollbar(widget.frame, orient='vertical', command=widget.yview)
        widget.vbar.pack(side='right', fill='y')
        widget.configure(yscrollcommand=widget.vbar.set)

    @staticmethod
    def _status_pair(parent, column, label, variable) -> None:
        ttk.Label(parent, text=label).grid(row=0, column=column, sticky="w")
        value = ttk.Label(parent, textvariable=variable, font=("Segoe UI", 10, "bold"), width=15, wraplength=130)
        value.grid(
            row=1, column=column, sticky="ew"
        )
        parent.bind('<Configure>', lambda e: value.configure(wraplength=max(80, e.width // 5 - 12)), add='+')

    def _selected_flow_id(self) -> int | None:
        selection = self.flow_list.curselection()
        if not selection:
            return None
        return self.selection.options[selection[0]].id

    def _refresh_flow_list(self, selected_id: int | None = None) -> None:
        self.flow_list.delete(0, "end")
        selected_index = None
        for index, item in enumerate(self.selection.options):
            mark = "x" if item.enabled else " "
            self.flow_list.insert("end", f"{index + 1:02d}. [{mark}] {item.display_name}")
            if item.id == selected_id:
                selected_index = index
        if selected_index is None and self.selection.options:
            selected_index = 0
        if selected_index is not None:
            self.flow_list.selection_set(selected_index)
            self.flow_list.activate(selected_index)
        self._load_step_settings()

    def _toggle_flow(self) -> None:
        flow_id = self._selected_flow_id()
        if flow_id is None:
            self._validation_error("Select a flow first")
            return
        self.selection.toggle(flow_id)
        self._refresh_flow_list(flow_id)

    def _move_up(self) -> None:
        self._move_selected(up=True)

    def _move_down(self) -> None:
        self._move_selected(up=False)

    def _move_selected(self, *, up: bool) -> None:
        flow_id = self._selected_flow_id()
        if flow_id is None:
            self._validation_error("Select a flow first")
            return
        moved = self.selection.move_up(flow_id) if up else self.selection.move_down(flow_id)
        self._refresh_flow_list(flow_id + (-1 if up else 1) if moved else flow_id)

    def _refresh_routines(self):
        if self.selection.draft and hasattr(self,'resource_snapshot_var'):
            self.resource_snapshot_var.set(self.selection.draft.resource_snapshot_mode)
            if hasattr(self, "relief_scroll"):
                self._load_relief_settings()
        self.routine_select.configure(values=tuple(r.name for r in self.selection.routines))
        index = next((i for i, r in enumerate(self.selection.routines)
                      if r.id == self.selection.selected_id), -1)
        if index >= 0:
            self.routine_select.current(index)
            self.routine_var.set(self.selection.draft.name)
        else:
            self.routine_var.set("")

    def _keep_draft(self):
        saved = next((r for r in self.selection.routines if r.id == self.selection.selected_id), None)
        if self.selection.draft == saved:
            return True
        answer = self._ask_confirmation("Unsaved routine", "Save changes before switching routines?", cancel=True)
        if answer is None:
            return False
        return self._save_routine() if answer else True

    def _select_routine(self, _event=None):
        index = self.routine_select.current()
        if index >= 0 and self._keep_draft():
            self.selection.select(self.selection.routines[index].id)
            self._refresh_flow_list()
        self._refresh_routines()

    def _new_routine(self, duplicate=False):
        if not self._keep_draft():
            return
        name = self._ask_string("Routine", "Routine name:",
            initialvalue=(self.selection.draft.name + " copy" if duplicate and self.selection.draft else ""))
        if name:
            try:
                self.selection.create(name, duplicate=duplicate)
                self._refresh_routines()
                self._refresh_flow_list()
            except ValueError as error:
                self._validation_error(str(error))

    def _duplicate_routine(self):
        self._new_routine(duplicate=True)

    def _rename_routine(self):
        if self.selection.draft is None:
            return
        name = self._ask_string("Rename routine", "Routine name:",
                                      initialvalue=self.selection.draft.name)
        if name:
            try:
                self.selection.rename(name)
                self.routine_var.set(self.selection.draft.name)
            except ValueError as error:
                self._validation_error(str(error))

    def _save_routine(self):
        try:
            self.selection.save()
            self._refresh_routines()
            self.result_var.set(f"Routine saved: {self.selection.store.path}")
            return True
        except (OSError, ValueError) as error:
            self._validation_error(str(error))
            return False

    def _delete_routine(self):
        if self.selection.draft is None:
            return
        if self._ask_confirmation("Delete routine", f'Delete "{self.selection.draft.name}"?'):
            try:
                self.selection.delete()
                self._refresh_routines()
                self._refresh_flow_list()
            except OSError as error:
                self._validation_error(str(error))

    def _add_step(self):
        index = self.available_flow_select.current()
        if index < 0:
            return
        try:
            self.selection.add(self.selection.registry.definitions[index].id)
            self._refresh_flow_list(len(self.selection.options) - 1)
        except ValueError as error:
            self._validation_error(str(error))

    def _remove_step(self):
        index = self._selected_flow_id()
        if index is not None:
            self.selection.remove(index)
            self._refresh_flow_list(min(index, len(self.selection.options) - 1))

    def _build_relief_settings(self, settings):
        self.relief_scroll = ScrollableSettings(settings)
        settings.add(self.relief_scroll, text='Reliefs')
        content = self.relief_scroll.content
        row = 0
        self.relief_controls = []
        def heading(text):
            nonlocal row
            ttk.Label(content, text=text, font=('Segoe UI', 11, 'bold')).grid(row=row, column=0, sticky='w', pady=(12, 5))
            row += 1
        def note(text):
            nonlocal row
            ttk.Label(content, text=text, wraplength=340, style='Muted.TLabel').grid(row=row, column=0, sticky='ew', pady=5)
            row += 1
        def check(text, var):
            nonlocal row
            widget = ttk.Checkbutton(content, text=text, variable=var, command=self._apply_relief_settings)
            widget.grid(row=row, column=0, sticky='w', pady=3)
            self.relief_controls.append(widget)
            row += 1
        note('Whole routine. Changes update the draft; Save Routine persists them.')
        heading('Socket Relief')
        check('Enhance All', self.socket_enhance_var)
        check('Sell incompatible opals', self.socket_sell_var)
        heading('Equipment Relief')
        note('Sell Equipment - checked means allow selling. Ethereal+ is always protected.')
        note('Sell Ethereal equipment of these types:')
        for kind, var in self.ethereal_type_vars.items():
            check('Sell Ethereal ' + ('Earrings' if kind.value == 'earring' else kind.value.title()), var)
        check('Sell Ethereal Enhance', self.ethereal_enhance_var)
        heading('Crafting Material Relief')
        note('Craft categories:')
        for family, var in self.craft_category_vars.items():
            check({'weapon': 'Weapon', 'armor': 'Armor', 'accessory': 'Accessories'}[family.value], var)
        heading('Treasure Relief')
        check('Open Gold Keys for safe capacity relief', self.treasure_gold_var)
        self.routine_controls.extend(self.relief_controls)
        self.relief_scroll.bind_content()

    def _load_relief_settings(self):
        policy = ReliefPolicy.from_dict(self.selection.draft.relief_policy)
        self.socket_enhance_var.set(policy.socket.enhance_all)
        self.socket_sell_var.set(policy.socket.sell_incompatible)
        for kind, variable in self.ethereal_type_vars.items():
            variable.set(kind in policy.equipment_sell.ethereal_types)
        self.ethereal_enhance_var.set(policy.equipment_sell.ethereal_enhance)
        for family, variable in self.craft_category_vars.items():
            variable.set(family in policy.craft_categories)
        self.treasure_gold_var.set(policy.treasure_gold_keys)

    def _apply_relief_settings(self):
        if self.selection.draft is None or self.controller.is_running:
            return
        policy = ReliefPolicy(SocketReliefPolicy(self.socket_enhance_var.get(), self.socket_sell_var.get()),
            self._equipment_sell_policy(), frozenset(f for f, v in self.craft_category_vars.items() if v.get()),
            self.treasure_gold_var.get())
        self.selection.configure_reliefs(policy.to_dict())
        self.result_var.set('Reliefs applied to routine draft; Save Routine to persist')

    def _load_step_settings(self):
        index = self._selected_flow_id()
        self._settings_step_index = index
        if index is None:
            if hasattr(self, 'step_scroll'):
                self._render_step_settings(None)
            return
        step = self.selection.draft.steps[index]
        # Reset every variable on selection, including after an invalid legacy config.
        values = {}
        try:
            values = config_overrides(step.config)
        except (TypeError, ValueError) as error:
            self.result_var.set(f"Invalid step settings: {error}; apply valid settings to repair")
        mw = values.get("monster_wave", MonsterWaveConfig())
        self.purchase_skip_var.set(mw.purchase_skip_tickets)
        self.continue_full_var.set(mw.continue_when_nonblocking_inventory_full)
        if hasattr(self, 'wb_eligibility_var'):
            self.wb_eligibility_var.set(step.config.get('world_boss', {}).get('eligibility', WorldBossEligibilityMode.DAILY_QUEST.value))
        if hasattr(self, 'step_scroll'):
            self._render_step_settings(step)

    def _render_step_settings(self, step):
        content = self.step_scroll.content
        for widget in content.winfo_children():
            widget.destroy()
        self.step_controls = []
        sections = STEP_CONFIG_SECTIONS.get(step.flow_id, ()) if step else ()
        self.visible_step_sections = sections
        index = self._settings_step_index
        label = self.selection.options[index].display_name if step else 'Select a step'
        self.step_heading_var.set(f'Step {index + 1} · {label}' if step else label)
        row = 0
        def note(text):
            nonlocal row
            widget = ttk.Label(content, text=text, wraplength=340, style='Muted.TLabel')
            widget.grid(row=row, column=0, sticky='ew', pady=(4, 10))
            row += 1
        if not sections:
            note('No configurable settings for this step.' if step else 'Select a step to configure its occurrence.')
        if 'world_boss' in sections:
            ttk.Label(content, text='Eligibility').grid(row=row, column=0, sticky='w', pady=(4, 6))
            row += 1
            self.wb_select = ttk.Combobox(content, textvariable=self.wb_eligibility_var,
                values=tuple(m.value for m in WorldBossEligibilityMode), state='readonly', width=30)
            self.wb_select.grid(row=row, column=0, sticky='ew')
            row += 1
            self.step_controls.append(self.wb_select)
            note('Eligibility applies only to this World Boss occurrence.')
        if 'monster_wave' in sections:
            ttk.Label(content, text='Monster Wave' if step.flow_id == 'monster_wave' else 'Monster Wave prerequisite / investment',
                      font=('Segoe UI', 10, 'bold')).grid(row=row, column=0, sticky='w', pady=6)
            row += 1
            for text, variable in (('Purchase SKIP tickets', self.purchase_skip_var),
                    ('Continue with nonblocking inventory full', self.continue_full_var)):
                check = ttk.Checkbutton(content, text=text, variable=variable)
                check.grid(row=row, column=0, sticky='w', pady=3)
                row += 1
                self.step_controls.append(check)
        running = self.controller.is_running
        for widget in self.step_controls:
            widget.configure(state='disabled' if running else 'readonly' if isinstance(widget, ttk.Combobox) else 'normal')
        self.apply_step_button.configure(state='normal' if sections and not running else 'disabled')
        self.step_scroll.reset()
        self.step_scroll.bind_content()
        self.theme.style_widgets(self.step_scroll)

    def _apply_step_settings(self):
        index = self._selected_flow_id()
        # The form must still describe the selected occurrence when Apply is delivered.
        if index is None or index != self._settings_step_index:
            return
        step = self.selection.draft.steps[index]
        sections = STEP_CONFIG_SECTIONS.get(step.flow_id, ())
        if not sections:
            return
        settings = dict(step.config)  # retain legacy overrides that this form does not own
        current = step_settings(MonsterWaveConfig(self.purchase_skip_var.get(), self.continue_full_var.get()),
                                self._equipment_sell_policy())
        current['world_boss'] = {'eligibility': self.wb_eligibility_var.get()} if 'world_boss' in sections else {}
        for section in sections:
            settings[section] = current[section]
        try:
            self.selection.configure(index, settings)
            self.result_var.set(f"Settings applied to step {index + 1}; Save Routine to persist")
        except (TypeError, ValueError) as error:
            self._validation_error(str(error))

    def _change_appearance(self, _event=None):
        self.theme.apply(self.appearance_var.get())
        try:
            self.preferences.save(self.appearance_var.get())
        except OSError as error:
            self.result_var.set(f'Appearance applied; unable to save preference: {error}')

    def _ask_string(self, title, prompt, initialvalue=''):
        return AppDialog(self.root, self.theme, title, prompt, initialvalue=initialvalue,
                         choices=('OK', 'Cancel')).result

    def _ask_confirmation(self, title, prompt, *, cancel=False):
        answer = AppDialog(self.root, self.theme, title, prompt,
                           choices=('Yes', 'No', 'Cancel') if cancel else ('Yes', 'No')).result
        return None if answer is None else answer == 'Yes'

    def _set_snapshot_mode(self, _event=None):
        if self.selection.draft:
            self.selection.set_resource_snapshot_mode(self.resource_snapshot_var.get())
            self.result_var.set('Resource snapshot setting applied; Save to persist')

    def _sort_character_state(self, column):
        if column == self.character_sort_column:
            self.character_sort_descending = not self.character_sort_descending
        else:
            self.character_sort_column = column
            self.character_sort_descending = False
        self._project_character_sort()

    def _project_character_sort(self):
        column = self.character_sort_column or 'Character'
        for index, row in enumerate(sorted_character_rows(self._character_rows, column, self.character_sort_descending)):
            self.character_table.move(row['character_id'], '', index)
        for name in CHARACTER_SORT_FIELDS:
            direction = ' ↓' if self.character_sort_descending else ' ↑'
            self.character_table.heading(name, text=name + (direction if name == self.character_sort_column else ''))

    def _refresh_character_state(self):
        if not self.root.winfo_exists():
            return
        if getattr(self, "_character_refresh_after", None):
            self.root.after_cancel(self._character_refresh_after)
            self._character_refresh_after = None
        try:
            rows=self.character_store.rows()  # catch-up before displaying
            self._character_rows = rows
            clock=self.character_store.clock.state()
            self.reset_clock_var.set('Reset clock: waiting for WB countdown' if clock is None else
                f"Next reset: {datetime.fromtimestamp(clock['next_daily']).astimezone().strftime('%Y-%m-%d %H:%M')} | WB {'open' if clock['wb_open'] else 'closed'}")
            for row in rows:
                cid=row['character_id']
                ads_at=row['ads_updated_at']
                observed=row['resource_observed_at']
                local_time=lambda at: datetime.fromtimestamp(at).astimezone().strftime('%m-%d %H:%M') if at is not None else '—'
                values=(row['display_name'],row['stage_ads_remaining'] if row['stage_ads_remaining'] is not None else 'UNKNOWN',
                    f"{row['ads_last_attempt_status'] or row['ads_status'] or 'UNKNOWN'} / {local_time(row['ads_last_attempt_at'] if row['ads_last_attempt_at'] is not None else ads_at)}",
                    'UNKNOWN' if row['wb_participated'] is None else 'YES' if row['wb_participated'] else 'NO',
                    f"{row['wb_cycle_id'] or 'UNKNOWN'} / {'open' if clock and clock['wb_open'] else 'closed' if clock else 'UNKNOWN'}",
                    *(row[k] if row[k] is not None else '—' for k in ('lapiz','dark_essence','light_essence','nature_essence','k_coins')),
                    local_time(observed))
                if self.character_table.exists(cid):
                    self.character_table.item(cid,values=values)
                else:
                    self.character_table.insert('', 'end',iid=cid,values=values)
            if hasattr(self, "character_sort_column"):
                self._project_character_sort()
            boundary=self.character_store.clock.next_transition()
            delay=5000 if boundary is None else max(50,min(5000,int((boundary-self.character_store.now())*1000)))
            self._character_refresh_after = self.root.after(delay,self._refresh_character_state)
        except Exception as error:
            self.reset_clock_var.set(f'Character state unavailable: {error}')
            self._character_refresh_after = self.root.after(5000,self._refresh_character_state)

    def _execution_request(self, character_count=None):
        kwargs = dict(debug=self.debug_var.get(), dotenv_path=self.dotenv_path, log_dir=self.log_dir)
        if isinstance(self.selection, RoutineEditor):
            if self.selection.draft is None:
                raise ValueError("Create a routine first")
            return GuiExecutionRequest.for_routine(self.selection.draft, self.selection.registry,
                                                   character_count=character_count, **kwargs)
        kwargs["equipment_sell"] = self._equipment_sell_policy()
        return (GuiExecutionRequest.selected_flows(self.selection.active_ids, **kwargs)
                if character_count is None else GuiExecutionRequest.session(
                    self.selection.active_ids, character_count, **kwargs))

    def _equipment_sell_policy(self):
        return EquipmentSellPolicy(
            frozenset(kind for kind, var in self.ethereal_type_vars.items() if var.get()),
            self.ethereal_enhance_var.get(),
        )

    def _run_selected_flows(self) -> None:
        try:
            request = self._execution_request()
            self._start(request)
        except (ValueError, RuntimeError) as error:
            self._validation_error(str(error))

    def _run_session(self) -> None:
        try:
            count = int(self.characters_var.get())
            request = self._execution_request(count)
            self._start(request)
        except (ValueError, RuntimeError) as error:
            self._validation_error(str(error))

    def _run_character_data_sweep(self):
        try:
            self._start(GuiExecutionRequest.character_data_sweep(debug=self.debug_var.get(),
                dotenv_path=self.dotenv_path,log_dir=self.log_dir))
        except (ValueError,RuntimeError) as error:
            self._validation_error(str(error))

    def _start(self, request: GuiExecutionRequest) -> None:
        self.progress = GuiProgress(character="1 / 1" if request.character_count == 1 else "-")
        self._active_mode = request.mode
        if request.mode in (GuiRunMode.SESSION,GuiRunMode.CHARACTER_DATA_SWEEP):
            self.session_elapsed_var.set(self.session_timer.start())
        self._debug_for_run = request.debug
        self.status_var.set(GuiRunStatus.RUNNING.value)
        self.result_var.set("Running...")
        self.log_var.set("Log: preparing...")
        self._sync_progress()
        self.controller.start(request)
        self._show_report(None)
        self.output_tabs.select(self.console_frame)
        self._set_running_controls(True)

    def _stop_safely(self) -> None:
        if self.controller.stop_safely():
            self.status_var.set(GuiRunStatus.STOPPING.value)
            self.state_var.set("Waiting for safe boundary")

    def _drain_worker(self) -> None:
        lines = []
        for message in self.controller.drain(limit=250):
            if message.kind is GuiMessageKind.EVENT:
                event = message.event
                assert event is not None
                self.progress.apply(event, self.selection.registry)
                if event.event == "runtime.started" and event.fields.get("log_path"):
                    self.log_var.set(f"Log: {event.fields['log_path']}")
                if event_visible(event, debug=self._debug_for_run):
                    lines.append(format_runtime_event(event))
            else:
                result = message.result
                assert result is not None
                self._finish(result)
        if lines:
            self._append_console(lines)
        self._sync_progress()
        if self._close_when_idle and not self.controller.is_running:
            self.character_store.close()
            self.root.after_idle(self.root.destroy)
            return
        self.root.after(POLL_INTERVAL_MS, self._drain_worker)

    def _finish(self, result: GuiExecutionResult) -> None:
        sweep = self._active_mode is GuiRunMode.CHARACTER_DATA_SWEEP
        if self._active_mode in (GuiRunMode.SESSION,GuiRunMode.CHARACTER_DATA_SWEEP):
            self.session_elapsed_var.set(self.session_timer.finish(result.duration))
        self._active_mode = None
        self.status_var.set(result.status.value)
        self.progress.state = result.status.value
        summary = (
            f"{result.status.value.upper()}  duration={result.duration:.1f}s  "
            f"characters={result.characters_processed}  flows={result.flows_completed}  "
            f"advances={result.advances_completed}  business_events={result.business_event_count}"
        )
        if result.error:
            summary += f"  cause={result.error} (see Debug Log)"
        if sweep:
            summary = (f"Character Data Sweep: {result.status.value} | {result.characters_processed} processed | "
                f"{result.identities_resolved} identities\n{result.snapshots_updated} snapshots updated | "
                f"{result.advances_completed} Rotations | {result.acquisition_failures} acquisition failures | {result.duration:.1f}s")
            if result.error:
                summary += f" | cause={result.error} (see Debug Log)"
        self.result_var.set(summary)
        self.log_var.set(f"Log: {result.log_path}")
        self._show_report(result.report)
        self._set_running_controls(False)

    def _show_report(self, report) -> None:
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("end", render_session_report(report) if report is not None else "No session report available.")
        self.report_text.configure(state="disabled")
        self.report_text.yview_moveto(0)
        refs = report_evidence_refs(report)
        self.evidence_select.configure(values=refs)
        self.evidence_var.set(refs[0] if refs else "")
        self.evidence_button.configure(state="normal" if refs else "disabled")
        self.evidence_status_var.set("")
        if report is not None:
            self.output_tabs.select(self.report_frame)

    def _locate_evidence(self) -> None:
        self.evidence_status_var.set(locate_evidence(self.evidence_var.get()))

    def _refresh_session_timer(self) -> None:
        if self.session_timer.running:
            self.session_elapsed_var.set(self.session_timer.update())
        self.root.after(SESSION_TIMER_INTERVAL_MS, self._refresh_session_timer)

    def _sync_progress(self) -> None:
        self.character_var.set(self.progress.character)
        self.flow_var.set(self.progress.flow)
        self.state_var.set(self.progress.state)

    def _set_running_controls(self, running: bool) -> None:
        if hasattr(self,'sweep_button'):
            self.sweep_button.configure(state='disabled' if running else 'normal')
        for check in getattr(self, "step_controls", self.sell_policy_checks):
            check.configure(state="disabled" if running else "readonly" if isinstance(check, ttk.Combobox) else "normal")
        for widget in getattr(self, "routine_controls", ()):
            widget.configure(state="disabled" if running else "readonly" if isinstance(widget,ttk.Combobox) else "normal")
        for name in ("routine_select", "available_flow_select"):
            if hasattr(self, name):
                getattr(self, name).configure(state="disabled" if running else "readonly")
        configure_state = "disabled" if running else "normal"
        for widget in (
            self.flow_list,
            self.toggle_button,
            self.up_button,
            self.down_button,
            self.characters,
            self.debug_check,
            self.run_flow_button,
            self.run_session_button,
        ):
            widget.configure(state=configure_state)
        self.stop_button.configure(state="normal" if running else "disabled")
        if hasattr(self, "apply_step_button"):
            self.apply_step_button.configure(state="normal" if self.visible_step_sections and not running else "disabled")

    def _append_console(self, lines: list[str]) -> None:
        at_bottom = self.console.yview()[1] >= 0.999
        self.console.configure(state="normal")
        self.console.insert("end", "\n".join(lines) + "\n")
        line_count = int(self.console.index("end-1c").split(".")[0])
        if line_count > MAX_VISIBLE_CONSOLE_LINES:
            self.console.delete("1.0", f"{line_count - MAX_VISIBLE_CONSOLE_LINES + 1}.0")
        self.console.configure(state="disabled")
        if at_bottom:
            self.console.see("end")

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _copy_selected(self) -> None:
        try:
            text = self.console.get("sel.first", "sel.last")
        except tk.TclError:
            self.result_var.set("No console text selected")
            return
        self._copy_text(text)

    def _copy_all(self) -> None:
        self._copy_text(self.console.get("1.0", "end-1c"))

    def _copy_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _validation_error(self, message: str) -> None:
        self.status_var.set("Validation error")
        self.result_var.set(message)

    def _on_close(self) -> None:
        if not self.controller.is_running:
            if not self._keep_draft():
                return
            self.root.destroy()
            self.character_store.close()
            return
        if not self._ask_confirmation(
            "Kritika FarmBot",
            "A run is active. Request Stop Safely and close when it finishes?",
        ):
            return
        self._close_when_idle = True
        self._stop_safely()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Unable to start Tkinter GUI: {error}")
        return 2
    KritikaFarmBotGui(root, dotenv_path=args.dotenv, log_dir=args.log_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
