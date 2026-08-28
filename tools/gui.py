"""Operational Tkinter frontend for the productive Kritika FarmBot runtime."""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from bot.config import DEFAULT_CHARACTER_COUNT
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
    event_visible,
)
from bot.productive_runtime import PROJECT_ROOT


POLL_INTERVAL_MS = 50
MAX_VISIBLE_CONSOLE_LINES = 5000


class KritikaFarmBotGui:
    """Tk widgets only; product execution remains in GuiRuntimeController."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
    ) -> None:
        self.root = root
        self.dotenv_path = Path(dotenv_path)
        self.log_dir = Path(log_dir)
        self.selection = FlowSelectionModel()
        self.controller = GuiRuntimeController(registry=self.selection.registry)
        self.progress = GuiProgress()
        self._debug_for_run = False
        self._close_when_idle = False

        root.title("Kritika FarmBot")
        root.geometry("920x680")
        root.minsize(760, 560)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.characters_var = tk.StringVar(value=str(DEFAULT_CHARACTER_COUNT))
        self.debug_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=GuiRunStatus.IDLE.value)
        self.character_var = tk.StringVar(value="-")
        self.flow_var = tk.StringVar(value="-")
        self.state_var = tk.StringVar(value="-")
        self.result_var = tk.StringVar(value="Ready")
        self.log_var = tk.StringVar(value="Log: -")

        self._build_layout()
        self._refresh_flow_list()
        self._set_running_controls(False)
        self.root.after(POLL_INTERVAL_MS, self._drain_worker)

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(outer, text="Kritika FarmBot", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)

        flows = ttk.LabelFrame(controls, text="Flows", padding=8)
        flows.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        flows.columnconfigure(0, weight=1)
        self.flow_list = tk.Listbox(flows, height=5, exportselection=False)
        self.flow_list.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.flow_list.bind("<Double-Button-1>", lambda _: self._toggle_flow())
        self.flow_list.bind("<space>", lambda _: self._toggle_flow())
        self.toggle_button = ttk.Button(flows, text="Enable / Disable", command=self._toggle_flow)
        self.toggle_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.up_button = ttk.Button(flows, text="↑ Up", command=self._move_up)
        self.up_button.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)
        self.down_button = ttk.Button(flows, text="↓ Down", command=self._move_down)
        self.down_button.grid(row=2, column=1, sticky="ew", padx=(8, 0))

        run = ttk.LabelFrame(controls, text="Execution", padding=8)
        run.grid(row=0, column=1, sticky="ns")
        ttk.Label(run, text="Characters").grid(row=0, column=0, sticky="w")
        self.characters = ttk.Spinbox(
            run,
            from_=1,
            to=999,
            width=8,
            textvariable=self.characters_var,
        )
        self.characters.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.debug_check = ttk.Checkbutton(run, text="Debug Mode", variable=self.debug_var)
        self.debug_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=7)
        self.run_flow_button = ttk.Button(run, text="Run Flow Once", command=self._run_flow_once)
        self.run_flow_button.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.run_session_button = ttk.Button(run, text="Run Session", command=self._run_session)
        self.run_session_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        self.stop_button = ttk.Button(run, text="Stop Safely", command=self._stop_safely)
        self.stop_button.grid(row=4, column=0, columnspan=2, sticky="ew")

        status = ttk.LabelFrame(outer, text="Status / Progress", padding=8)
        status.grid(row=2, column=0, sticky="ew", pady=10)
        for column in range(4):
            status.columnconfigure(column, weight=1)
        self._status_pair(status, 0, "Status", self.status_var)
        self._status_pair(status, 1, "Character", self.character_var)
        self._status_pair(status, 2, "Flow", self.flow_var)
        self._status_pair(status, 3, "State", self.state_var)
        ttk.Label(status, text="Result:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(status, textvariable=self.result_var).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Label(status, textvariable=self.log_var).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(3, 0)
        )

        console_frame = ttk.LabelFrame(outer, text="Debug Console", padding=8)
        console_frame.grid(row=3, column=0, sticky="nsew")
        console_frame.columnconfigure(0, weight=1)
        console_frame.rowconfigure(0, weight=1)
        self.console = ScrolledText(
            console_frame,
            wrap="none",
            height=18,
            font=("Consolas", 9),
            state="disabled",
        )
        self.console.grid(row=0, column=0, columnspan=3, sticky="nsew")
        ttk.Button(console_frame, text="Clear", command=self._clear_console).grid(
            row=1, column=0, sticky="w", pady=(7, 0)
        )
        ttk.Button(console_frame, text="Copy selected", command=self._copy_selected).grid(
            row=1, column=1, pady=(7, 0)
        )
        ttk.Button(console_frame, text="Copy all", command=self._copy_all).grid(
            row=1, column=2, sticky="e", pady=(7, 0)
        )

    @staticmethod
    def _status_pair(parent, column, label, variable) -> None:
        ttk.Label(parent, text=label).grid(row=0, column=column, sticky="w")
        ttk.Label(parent, textvariable=variable, font=("Segoe UI", 10, "bold")).grid(
            row=1, column=column, sticky="w"
        )

    def _selected_flow_id(self) -> str | None:
        selection = self.flow_list.curselection()
        if not selection:
            return None
        return self.selection.options[selection[0]].id

    def _refresh_flow_list(self, selected_id: str | None = None) -> None:
        self.flow_list.delete(0, "end")
        selected_index = None
        for index, item in enumerate(self.selection.options):
            mark = "x" if item.enabled else " "
            self.flow_list.insert("end", f"[{mark}] {item.display_name}")
            if item.id == selected_id:
                selected_index = index
        if selected_index is None and self.selection.options:
            selected_index = 0
        if selected_index is not None:
            self.flow_list.selection_set(selected_index)
            self.flow_list.activate(selected_index)

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
        if up:
            self.selection.move_up(flow_id)
        else:
            self.selection.move_down(flow_id)
        self._refresh_flow_list(flow_id)

    def _run_flow_once(self) -> None:
        try:
            request = GuiExecutionRequest.flow_once(
                self.selection.active_ids,
                debug=self.debug_var.get(),
                dotenv_path=self.dotenv_path,
                log_dir=self.log_dir,
            )
            self._start(request)
        except (ValueError, RuntimeError) as error:
            self._validation_error(str(error))

    def _run_session(self) -> None:
        try:
            count = int(self.characters_var.get())
            request = GuiExecutionRequest.session(
                self.selection.active_ids,
                count,
                debug=self.debug_var.get(),
                dotenv_path=self.dotenv_path,
                log_dir=self.log_dir,
            )
            self._start(request)
        except (ValueError, RuntimeError) as error:
            self._validation_error(str(error))

    def _start(self, request: GuiExecutionRequest) -> None:
        self.progress = GuiProgress(character="1 / 1" if request.character_count == 1 else "-")
        self._debug_for_run = request.debug
        self.status_var.set(GuiRunStatus.RUNNING.value)
        self.result_var.set("Running...")
        self.log_var.set("Log: preparing...")
        self._sync_progress()
        self.controller.start(request)
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
            self.root.after_idle(self.root.destroy)
            return
        self.root.after(POLL_INTERVAL_MS, self._drain_worker)

    def _finish(self, result: GuiExecutionResult) -> None:
        self.status_var.set(result.status.value)
        self.progress.state = result.status.value
        summary = (
            f"{result.status.value.upper()}  duration={result.duration:.1f}s  "
            f"characters={result.characters_processed}  flows={result.flows_completed}  "
            f"advances={result.advances_completed}  business_events={result.business_event_count}"
        )
        if result.error:
            summary += f"  cause={result.error} (see Debug Log)"
        self.result_var.set(summary)
        self.log_var.set(f"Log: {result.log_path}")
        self._set_running_controls(False)

    def _sync_progress(self) -> None:
        self.character_var.set(self.progress.character)
        self.flow_var.set(self.progress.flow)
        self.state_var.set(self.progress.state)

    def _set_running_controls(self, running: bool) -> None:
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
            self.root.destroy()
            return
        if not messagebox.askyesno(
            "Kritika FarmBot",
            "A run is active. Request Stop Safely and close when it finishes?",
            parent=self.root,
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
