"""Ordered composition and local persistence; gameplay stays in registered flows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import json
from pathlib import Path
from uuid import uuid4

from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import EquipmentType
from bot.monster_wave_config import MonsterWaveConfig
from bot.character_data import ResourceSnapshotMode
from bot.world_boss_state import WorldBossEligibilityMode


SCHEMA_VERSION = 1


def config_overrides(config: dict) -> dict:
    """Reconstruct canonical config objects, never duplicate their policy fields."""
    if not isinstance(config, dict) or set(config) - {"monster_wave", "equipment_sell", "world_boss"}:
        raise ValueError("unsupported step configuration")
    overrides = {}
    if 'world_boss' in config:
        value = config['world_boss']
        if not isinstance(value, dict) or set(value) != {'eligibility'}:
            raise ValueError('Invalid World Boss settings')
        WorldBossEligibilityMode(value['eligibility'])
    if "monster_wave" in config:
        overrides["monster_wave"] = MonsterWaveConfig(**config["monster_wave"])
    if "equipment_sell" in config:
        value = dict(config["equipment_sell"])
        if "ethereal_types" in value:
            value["ethereal_types"] = frozenset(EquipmentType(t) for t in value["ethereal_types"])
        overrides["equipment_sell"] = EquipmentSellPolicy(**value)
    return overrides


def step_settings(monster_wave: MonsterWaveConfig, equipment_sell: EquipmentSellPolicy) -> dict:
    return {
        "monster_wave": asdict(monster_wave),
        "equipment_sell": {
            "ethereal_types": sorted(t.value for t in equipment_sell.ethereal_types),
            "ethereal_enhance": equipment_sell.ethereal_enhance,
        },
    }


@dataclass(frozen=True)
class RoutineStep:
    flow_id: str
    enabled: bool = True
    config: dict = field(default_factory=dict)
    continue_on_unavailable: bool = True

    def __post_init__(self):
        if not isinstance(self.flow_id, str) or not self.flow_id.strip():
            raise ValueError("flow_id must be a non-empty string")
        if type(self.enabled) is not bool or type(self.continue_on_unavailable) is not bool:
            raise ValueError("step flags must be bool")
        if not isinstance(self.config, dict):
            raise ValueError("step config must be an object")
        object.__setattr__(self, "config", deepcopy(self.config))


@dataclass(frozen=True)
class RoutineSpec:
    id: str
    name: str
    steps: tuple[RoutineStep, ...] = ()
    resource_snapshot_mode: str = ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("routine id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("routine name must be a non-empty string")
        if any(not isinstance(step, RoutineStep) for step in self.steps):
            raise ValueError("steps must contain RoutineStep")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, 'resource_snapshot_mode', ResourceSnapshotMode(self.resource_snapshot_mode).value)

    def active_steps(self, registry):
        available = {definition.id for definition in registry.definitions}
        return tuple(step for step in self.steps if step.enabled and step.flow_id in available)


def default_routines(registry):
    # Presets are ordinary editable specs. No runtime depends on these IDs.
    return (
        RoutineSpec("custom", "Custom", tuple(RoutineStep(d.id) for d in registry.definitions if d.id != "gold_farming")),
        RoutineSpec("basic-gold", "Basic Gold Farming", (RoutineStep("gold_farming"),)),
    )


class RoutineStore:
    """Recover valid entries individually and preserve unreadable files before saving."""

    def __init__(self, path: Path, registry):
        self.path, self.registry = Path(path), registry
        self.warnings: list[str] = []
        self._preserve_original = False

    def load(self):
        self.warnings = []
        self._preserve_original = False
        if not self.path.exists():
            return default_routines(self.registry), "custom"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != SCHEMA_VERSION:
                raise ValueError("unsupported routine schema version")
            if not isinstance(data.get("routines"), list):
                raise ValueError("routines must be an array")
        except (OSError, ValueError) as error:
            self.warnings.append(f"Cannot load routines: {error}; using defaults")
            self._preserve_original = True
            return default_routines(self.registry), "custom"
        routines = []
        ids = set()
        available = {d.id for d in self.registry.definitions}
        for raw in data["routines"]:
            try:
                if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
                    raise ValueError("invalid routine entry")
                mode = raw.get('resource_snapshot_mode', ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value)
                if not isinstance(mode,str) or mode not in {m.value for m in ResourceSnapshotMode}:
                    mode = ResourceSnapshotMode.OFF.value
                    self.warnings.append('Invalid resource snapshot mode; tracking OFF')
                base = RoutineSpec(raw["id"], raw["name"], resource_snapshot_mode=mode)
                if base.id in ids:
                    raise ValueError("duplicate routine id")
                steps = []
                for index, value in enumerate(raw["steps"]):
                    try:
                        value = deepcopy(value)
                        if isinstance(value, dict) and isinstance(value.get('config'), dict) and 'world_boss' in value['config']:
                            wb = value['config']['world_boss']
                            if not isinstance(wb, dict) or set(wb) != {'eligibility'} or not isinstance(wb.get('eligibility'),str) or wb.get('eligibility') not in {m.value for m in WorldBossEligibilityMode}:
                                value['config']['world_boss'] = {'eligibility':WorldBossEligibilityMode.DAILY_QUEST.value}
                                self.warnings.append('Invalid WB eligibility; using DAILY_QUEST')
                        step = RoutineStep(**value)
                        if step.flow_id not in available:
                            self.warnings.append(f"{base.name} #{index + 1}: unknown flow {step.flow_id}; retained, skipped")
                        else:
                            try:
                                config_overrides(step.config)
                            except (TypeError, ValueError) as error:
                                self.warnings.append(f"{base.name} #{index + 1}: invalid config ({error}); disabled")
                                step = replace(step, enabled=False)
                        steps.append(step)
                    except (TypeError, ValueError) as error:
                        self.warnings.append(f"{base.name} #{index + 1}: invalid step ({error}); skipped")
                        self._preserve_original = True
                legacy = tuple(RoutineStep(f) for f in ("stages_daily","monster_wave","stages_daily","monster_wave"))
                if (base.id == "basic-gold" and base.name == "Basic Gold Farming"
                    and tuple(steps) == legacy and "gold_farming" in available):
                    steps = [RoutineStep("gold_farming")]
                    self.warnings.append("Basic Gold Farming upgraded to Gold Farming Cycle; custom sequences preserved")
                routines.append(replace(base, steps=tuple(steps)))
                ids.add(base.id)
            except (KeyError, TypeError, ValueError) as error:
                self.warnings.append(f"Invalid routine ({error}); skipped")
                self._preserve_original = True
        # An intentionally empty library stays empty after deletion/reopen.
        if not routines and data["routines"]:
            routines = list(default_routines(self.registry))
        selected = data.get("selected_id")
        if not isinstance(selected, str) or selected not in {r.id for r in routines}:
            selected = routines[0].id if routines else None
        return tuple(routines), selected

    def save(self, routines, selected_id):
        payload = {"version": SCHEMA_VERSION, "selected_id": selected_id,
                   "routines": [asdict(routine) for routine in routines]}
        content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._preserve_original and self.path.exists():
            backup = self.path.with_name(f"{self.path.name}.{uuid4().hex}.bak")
            backup.write_bytes(self.path.read_bytes())
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(self.path)
        self._preserve_original = False


class RoutineEditor:
    """Tk-independent CRUD and positional editing, including repeated flows."""

    def __init__(self, store: RoutineStore):
        self.store, self.registry = store, store.registry
        routines, self.selected_id = store.load()
        self.routines = list(routines)
        self.draft = next((deepcopy(r) for r in routines if r.id == self.selected_id), None)

    @property
    def options(self):
        from bot.gui_model import GuiFlowOption
        values = []
        for index, step in enumerate(self.draft.steps if self.draft else ()):
            try:
                label = self.registry.get(step.flow_id).display_name
            except KeyError:
                label = f"Unavailable: {step.flow_id}"
            values.append(GuiFlowOption(index, label, step.enabled))
        return tuple(values)

    @property
    def active_ids(self):
        return tuple(s.flow_id for s in self.draft.active_steps(self.registry)) if self.draft else ()

    def select(self, routine_id):
        self.draft = deepcopy(next(r for r in self.routines if r.id == routine_id))
        self.selected_id = routine_id

    def create(self, name, *, duplicate=False):
        steps = deepcopy(self.draft.steps) if duplicate and self.draft else ()
        mode = self.draft.resource_snapshot_mode if duplicate and self.draft else ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value
        self.draft = RoutineSpec(uuid4().hex, name, steps, mode)
        self.selected_id = self.draft.id
        self.routines.append(deepcopy(self.draft))

    def rename(self, name):
        self.draft = replace(self.draft, name=name)

    def save(self):
        values = [deepcopy(self.draft) if r.id == self.selected_id else r for r in self.routines]
        self.store.save(values, self.selected_id)
        self.routines = values

    def delete(self):
        values = [r for r in self.routines if r.id != self.selected_id]
        selected = values[0].id if values else None
        self.store.save(values, selected)
        self.routines, self.selected_id = values, selected
        self.draft = deepcopy(values[0]) if values else None

    def add(self, flow_id):
        self.registry.get(flow_id)
        if self.draft is None:
            raise ValueError("Create a routine first")
        self.draft = replace(self.draft, steps=self.draft.steps + (RoutineStep(flow_id),))

    def remove(self, index):
        steps = list(self.draft.steps)
        steps.pop(index)
        self.draft = replace(self.draft, steps=tuple(steps))

    def configure(self, index, config):
        config_overrides(config)
        self._replace_step(index, config=config)

    def set_resource_snapshot_mode(self, mode):
        self.draft = replace(self.draft, resource_snapshot_mode=ResourceSnapshotMode(mode).value)

    def set_enabled(self, index, enabled):
        self._replace_step(index, enabled=enabled)

    def toggle(self, index):
        self.set_enabled(index, not self.draft.steps[index].enabled)

    def _replace_step(self, index, **changes):
        steps = list(self.draft.steps)
        steps[index] = replace(steps[index], **changes)
        self.draft = replace(self.draft, steps=tuple(steps))

    def move_up(self, index):
        return self._move(index, -1)

    def move_down(self, index):
        return self._move(index, 1)

    def _move(self, index, delta):
        steps = list(self.draft.steps)
        target = index + delta
        if not 0 <= target < len(steps):
            return False
        steps[index], steps[target] = steps[target], steps[index]
        self.draft = replace(self.draft, steps=tuple(steps))
        return True
