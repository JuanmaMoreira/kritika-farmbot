"""Small Tk-independent models for the operational GUI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from bot.config import DEFAULT_CHARACTER_COUNT
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.event_log import EventLevel, RuntimeEvent
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowRegistry
from bot.productive_runtime import PROJECT_ROOT
from bot.routines import RoutineSpec


@dataclass(frozen=True)
class GuiFlowOption:
    id: str | int
    display_name: str
    enabled: bool


class FlowSelectionModel:
    """Ordered enabled/disabled projection of the productive FlowRegistry."""

    def __init__(self, registry: FlowRegistry = DEFAULT_FLOW_REGISTRY) -> None:
        self.registry = registry
        self._order = [item.id for item in registry.definitions]
        self._enabled = set(self._order) - {"gold_farming"}  # Composite farming is explicitly selected.

    @property
    def options(self) -> tuple[GuiFlowOption, ...]:
        return tuple(
            GuiFlowOption(
                flow_id,
                self.registry.get(flow_id).display_name,
                flow_id in self._enabled,
            )
            for flow_id in self._order
        )

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(flow_id for flow_id in self._order if flow_id in self._enabled)

    def set_enabled(self, flow_id: str, enabled: bool) -> None:
        self.registry.get(flow_id)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be bool")
        if enabled:
            self._enabled.add(flow_id)
        else:
            self._enabled.discard(flow_id)

    def toggle(self, flow_id: str) -> None:
        self.set_enabled(flow_id, flow_id not in self._enabled)

    def move_up(self, flow_id: str) -> bool:
        return self._move(flow_id, -1)

    def move_down(self, flow_id: str) -> bool:
        return self._move(flow_id, 1)

    def _move(self, flow_id: str, delta: int) -> bool:
        self.registry.get(flow_id)
        index = self._order.index(flow_id)
        target = index + delta
        if target < 0 or target >= len(self._order):
            return False
        self._order[index], self._order[target] = self._order[target], self._order[index]
        return True


class GuiRunMode(str, Enum):
    FLOW_ONCE = "flow_once"
    SELECTED_FLOWS = "selected_flows"
    SESSION = "session"
    CHARACTER_DATA_SWEEP = "character_data_sweep"


class SessionElapsedTimer:
    """Monotonic presentation state for the productive Run Session timer."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._started_at: float | None = None
        self._elapsed = 0.0

    @property
    def running(self) -> bool:
        return self._started_at is not None

    @property
    def text(self) -> str:
        total_seconds = int(max(0.0, self._elapsed))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def start(self) -> str:
        self._started_at = self.clock()
        self._elapsed = 0.0
        return self.text

    def update(self) -> str:
        if self._started_at is not None:
            self._elapsed = max(0.0, self.clock() - self._started_at)
        return self.text

    def finish(self, duration: float) -> str:
        self._elapsed = max(0.0, float(duration))
        self._started_at = None
        return self.text


@dataclass(frozen=True)
class GuiExecutionRequest:
    mode: GuiRunMode
    flow_ids: tuple[str, ...]
    character_count: int = DEFAULT_CHARACTER_COUNT
    debug: bool = False
    dotenv_path: Path = PROJECT_ROOT / ".env"
    log_dir: Path = PROJECT_ROOT / "logs"
    equipment_sell: EquipmentSellPolicy = EquipmentSellPolicy()
    routine: RoutineSpec | None = field(default=None, kw_only=True)

    @classmethod
    def for_routine(cls, routine, registry, *, character_count=None, **kwargs):
        from copy import deepcopy
        from dataclasses import replace
        ids = tuple(step.flow_id for step in routine.active_steps(registry))
        request = (cls.selected_flows(ids, **kwargs) if character_count is None
                   else cls.session(ids, character_count, **kwargs))
        return replace(request, routine=deepcopy(routine))

    @classmethod
    def flow_once(
        cls,
        flow_ids,
        *,
        debug: bool = False,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
        equipment_sell: EquipmentSellPolicy = EquipmentSellPolicy(),
    ) -> "GuiExecutionRequest":
        values = tuple(flow_ids)
        if len(values) != 1:
            raise ValueError("Run Flow Once requires exactly one active flow")
        return cls(GuiRunMode.FLOW_ONCE, values, 1, debug, Path(dotenv_path), Path(log_dir), equipment_sell)

    @classmethod
    def character_data_sweep(cls, *, debug=False, dotenv_path=PROJECT_ROOT/'.env',log_dir=PROJECT_ROOT/'logs'):
        return cls(GuiRunMode.CHARACTER_DATA_SWEEP,(),DEFAULT_CHARACTER_COUNT,debug,Path(dotenv_path),Path(log_dir))

    @classmethod
    def selected_flows(
        cls, flow_ids, *, debug: bool = False,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
        equipment_sell: EquipmentSellPolicy = EquipmentSellPolicy(),
    ) -> "GuiExecutionRequest":
        values = tuple(flow_ids)
        if not values:
            raise ValueError("Run Selected Flows requires at least one active flow")
        return cls(GuiRunMode.SELECTED_FLOWS, values, 1, debug, Path(dotenv_path), Path(log_dir), equipment_sell)

    @classmethod
    def session(
        cls,
        flow_ids,
        character_count: int,
        *,
        debug: bool = False,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
        equipment_sell: EquipmentSellPolicy = EquipmentSellPolicy(),
    ) -> "GuiExecutionRequest":
        values = tuple(flow_ids)
        if not values:
            raise ValueError("Run Session requires at least one active flow")
        if isinstance(character_count, bool) or not isinstance(character_count, int) or character_count <= 0:
            raise ValueError("Characters must be a positive integer")
        return cls(
            GuiRunMode.SESSION,
            values,
            character_count,
            debug,
            Path(dotenv_path),
            Path(log_dir),
            equipment_sell,
        )


@dataclass
class GuiProgress:
    character: str = "-"
    flow: str = "-"
    state: str = "-"
    flows_completed: int = 0

    def apply(self, event: RuntimeEvent, registry: FlowRegistry = DEFAULT_FLOW_REGISTRY) -> None:
        name = event.event
        fields = event.fields
        if name == "session.character.started":
            self.character = f"{fields.get('character_index', '-')} / {fields.get('character_count', '-')}"
            self.state = "Running"
        elif name in {"flow.started", "flow.skipped_not_eligible"}:
            flow_id = fields.get("flow")
            try:
                self.flow = registry.get(str(flow_id)).display_name
            except KeyError:
                self.flow = str(flow_id or "-")
            self.state = ("Skipped (not eligible)" if name == "flow.skipped_not_eligible"
                          else "Running flow")
        elif name == "flow.completed":
            self.flows_completed += 1
        elif name == 'character_data_sweep.started':
            self.flow = 'Character Data Sweep'
        elif name == 'character.identity_resolved':
            self.character = f"{self.character} | {fields.get('display_name','-')}"
        elif name == 'character_data_sweep.snapshot':
            self.state = f"Snapshot: {fields.get('status','-')}"
        elif name == "rotation.started":
            if self.flow != 'Character Data Sweep':
                self.flow = "-"
            self.state = "Rotation"
        elif name in {"world_boss.wait.started", "controlled_wait.started"}:
            self.state = "Waiting"
        elif name == "session.completed":
            self.state = "Completed"
        elif name in {'flow.manual_resolution', 'session.manual_resolution'}:
            self.state = 'Manual resolution required'
        elif name == 'flow.controlled_unavailable':
            self.state = 'Unavailable (continuing)'


def event_visible(event: RuntimeEvent, *, debug: bool) -> bool:
    return debug or event.level >= EventLevel.INFO


# Occurrence decisions only; relief policy belongs to the whole routine.
STEP_CONFIG_SECTIONS = {
    'monster_wave': (),
    'stages_daily': (),
    'gold_farming': (),
    'world_boss': ('world_boss',),
}

CHARACTER_SORT_FIELDS = {
    'Character': 'display_name', 'Stage Ads': 'stage_ads_remaining',
    'Ads status / updated': 'ads_updated_at',
    'WB participated': 'wb_participated', 'WB cycle / status': 'wb_cycle_id',
    'Lapiz': 'lapiz',
    'Dark': 'dark_essence', 'Light': 'light_essence', 'Nature': 'nature_essence',
    'K Coins': 'k_coins', 'Resource snapshot': 'resource_observed_at',
}


def sorted_character_rows(rows, column='Character', descending=False):
    """GUI projection: numeric/time values stay typed, unknown last in both directions.

    WB ascending is NO, YES, UNKNOWN; descending YES, NO, UNKNOWN.
    Ties use canonical display order and permanent ID regardless of direction.
    """
    field = CHARACTER_SORT_FIELDS[column]
    ordered = sorted(rows, key=lambda r: (r['display_name'].casefold(), r['character_id']))
    def key(row):
        value = row[field]
        if field == 'ads_updated_at' and row.get('ads_last_attempt_at') is not None:
            value = row['ads_last_attempt_at']
        return value.casefold() if isinstance(value, str) else value
    known = [r for r in ordered if key(r) is not None]
    unknown = [r for r in ordered if key(r) is None]
    return sorted(known, key=key, reverse=descending) + unknown


__all__ = (
    "FlowSelectionModel",
    "GuiExecutionRequest",
    "GuiFlowOption",
    "GuiProgress",
    "GuiRunMode",
    "SessionElapsedTimer",
    "event_visible",
)
