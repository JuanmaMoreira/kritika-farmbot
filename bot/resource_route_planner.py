"""Pure deterministic planning for Monster Wave resource prerequisites.

The board owns description only.  This module combines that immutable
description with explicitly supplied non-board facts and returns symbolic
capability steps.  It performs no observation, navigation or execution.

The Monster Wave pair semantics are deliberately narrow: ``balance`` is the
currently displayed balance and ``displayed_limit`` is the displayed limit.
Neither value is an incoming reward, recipe or Trading ``have/need`` pair.
Entry thresholds authorize travel; execution drains visited capabilities
using fresh facts. Stochastic Monster Wave rewards do not enter this plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

from bot.monster_wave_board_reader import BOARD_ROWS, MonsterWaveBoardRow
from bot.monster_wave_board_snapshot import (
    BoardEvidence,
    BoardPopup,
    MonsterWaveBoardSnapshot,
)


BOARD_ITEM_IDS = tuple(row[0] for row in BOARD_ROWS)
KEY_ITEM_IDS = frozenset({"bronze_key", "silver_key"})
MATERIAL_ITEM_IDS = frozenset({"weapon_material", "hero_weapon_material"})
ENTRY_THRESHOLDS = {
    "bronze_key": 400, "silver_key": 450,
    "weapon_material": 800, "hero_weapon_material": 800,
}


class ResourceRouteStatus(str, Enum):
    READY = "ready"
    NO_PREREQUISITES = "no_prerequisites"
    INSUFFICIENT_OBSERVABILITY = "insufficient_observability"
    CONTRADICTORY = "contradictory"


class UnresolvedCode(str, Enum):
    MISSING_BOARD_SNAPSHOT = "missing_board_snapshot"
    FOREIGN_BOARD_SNAPSHOT = "foreign_board_snapshot"
    STALE_BOARD_SNAPSHOT = "stale_board_snapshot"
    BOARD_CONTENT_UNKNOWN = "board_content_unknown"
    CONTRADICTORY_BOARD = "contradictory_board"
    MISSING_INCOMING_REWARD = "missing_incoming_reward"
    CONTRADICTORY_NON_BOARD_FACTS = "contradictory_non_board_facts"
    ARENA_TICKET_ROUTE_NOT_ESTABLISHED = "arena_ticket_route_not_established"
    MISSING_MATERIAL_CONVERSION = "missing_material_conversion"
    UNSUPPORTED_MATERIAL_CONVERSION = "unsupported_material_conversion"
    MATERIAL_CONVERSION_NOT_ACTIONABLE = "material_conversion_not_actionable"
    MISSING_CRAFT_FACT = "missing_craft_fact"
    UNSUPPORTED_CRAFT_FACT = "unsupported_craft_fact"
    MISSING_EQUIPMENT_CAPACITY = "missing_equipment_capacity"
    CRAFT_ENTRY_CAPACITY_UNAVAILABLE = "craft_entry_capacity_unavailable"
    CRAFT_MATERIAL_UNAVAILABLE = "craft_material_unavailable"
    MULTI_CRAFT_POLICY_NOT_ESTABLISHED = "multi_craft_policy_not_established"


class PlanningEvidenceKind(str, Enum):
    BOARD_PAIR = "board_pair"
    INCOMING_REWARD = "incoming_reward"
    OVERFLOW = "overflow"
    CAPABILITY = "capability"
    ORDER = "order"
    WARNING = "warning"
    THRESHOLD = "threshold"


@dataclass(frozen=True)
class IncomingRewardFact:
    """Exact incoming Monster Wave reward, or ``None`` when not established."""

    item_id: str
    amount: int | None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id:
            raise ValueError("item_id must be a non-empty string")
        if self.amount is not None:
            _non_negative_int(self.amount, "amount")
        object.__setattr__(self, "evidence", _strings(self.evidence, "evidence"))


@dataclass(frozen=True)
class MaterialConversionFact:
    """Externally established Trading conversion for one board material."""

    source_item_id: str
    destination_item_id: str
    trading_item_id: str
    input_per_trade: int
    output_per_trade: int
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("source_item_id", "destination_item_id", "trading_item_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        _positive_int(self.input_per_trade, "input_per_trade")
        _positive_int(self.output_per_trade, "output_per_trade")
        object.__setattr__(self, "evidence", _strings(self.evidence, "evidence"))


@dataclass(frozen=True)
class CraftCapacityFact:
    """Externally established craft-first facts; never fetched by the planner."""

    material_item_id: str
    family: str
    tier: str
    material_per_craft: int
    free_equipment_slots: int | None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("material_item_id", "family", "tier"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        _positive_int(self.material_per_craft, "material_per_craft")
        if self.free_equipment_slots is not None:
            _non_negative_int(self.free_equipment_slots, "free_equipment_slots")
        object.__setattr__(self, "evidence", _strings(self.evidence, "evidence"))


@dataclass(frozen=True)
class NonBoardResourceFacts:
    incoming_rewards: tuple[IncomingRewardFact, ...] = ()
    material_conversions: tuple[MaterialConversionFact, ...] = ()
    craft_capacities: tuple[CraftCapacityFact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "incoming_rewards", tuple(self.incoming_rewards))
        object.__setattr__(self, "material_conversions", tuple(self.material_conversions))
        object.__setattr__(self, "craft_capacities", tuple(self.craft_capacities))
        _instances(self.incoming_rewards, IncomingRewardFact, "incoming_rewards")
        _instances(self.material_conversions, MaterialConversionFact, "material_conversions")
        _instances(self.craft_capacities, CraftCapacityFact, "craft_capacities")


@dataclass(frozen=True)
class ResourcePlanningInput:
    board: MonsterWaveBoardSnapshot | None
    non_board: NonBoardResourceFacts
    now: float
    after_sequence: int
    max_board_age_s: float = 2.0

    def __post_init__(self) -> None:
        if not isinstance(self.non_board, NonBoardResourceFacts):
            raise ValueError("non_board must be NonBoardResourceFacts")
        _time(self.now, "now")
        _time(self.max_board_age_s, "max_board_age_s")
        _non_negative_int(self.after_sequence, "after_sequence")


@dataclass(frozen=True)
class KeysPromotionStep:
    capability: str = "keys_promotion"

    def __post_init__(self) -> None:
        if self.capability != "keys_promotion":
            raise ValueError("Keys step must name the closed keys_promotion capability")


@dataclass(frozen=True)
class TradingMaterialOperation:
    trading_item_id: str
    source_item_id: str
    destination_item_id: str
    quantity: int | None = None

    def __post_init__(self) -> None:
        for name in ("trading_item_id", "source_item_id", "destination_item_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        if self.quantity is not None:
            _positive_int(self.quantity, "quantity")


@dataclass(frozen=True)
class TradingMaterialsStep:
    operations: tuple[TradingMaterialOperation, ...] = (
        TradingMaterialOperation(
            "hero_weapon_crafting_material", "weapon_material",
            "hero_weapon_material",
        ),
    )
    capability: str = "trading_materials"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        if not self.operations:
            raise ValueError("Trading materials step needs at least one operation")
        _instances(self.operations, TradingMaterialOperation, "operations")
        if self.capability != "trading_materials":
            raise ValueError("Trading materials step must name its closed capability")


TradingSessionOperation = KeysPromotionStep | TradingMaterialsStep


@dataclass(frozen=True)
class TradingSessionStep:
    """One grouped Trading visit, with operations in deterministic order."""

    operations: tuple[TradingSessionOperation, ...]
    capability: str = "trading_session"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        if not self.operations:
            raise ValueError("Trading session needs at least one operation")
        if any(not isinstance(item, (KeysPromotionStep, TradingMaterialsStep))
               for item in self.operations):
            raise ValueError("Trading session contains an unsupported operation")
        if sum(isinstance(item, KeysPromotionStep) for item in self.operations) > 1:
            raise ValueError("Trading session cannot duplicate Keys promotion")
        if sum(isinstance(item, TradingMaterialsStep) for item in self.operations) > 1:
            raise ValueError("Trading session cannot duplicate materials")
        if self.capability != "trading_session":
            raise ValueError("Trading session must remain symbolic")


@dataclass(frozen=True)
class CraftStep:
    family: str
    tier: str
    quantity: int | None = None
    capability: str = "craft"

    def __post_init__(self) -> None:
        if not isinstance(self.family, str) or not self.family:
            raise ValueError("family must be a non-empty string")
        if not isinstance(self.tier, str) or not self.tier:
            raise ValueError("tier must be a non-empty string")
        if self.quantity is not None:
            _positive_int(self.quantity, "quantity")
        if self.capability != "craft":
            raise ValueError("Craft step must remain symbolic")


ResourceRouteStep = CraftStep | TradingSessionStep


@dataclass(frozen=True)
class UnresolvedReason:
    code: UnresolvedCode
    item_id: str | None = None
    required_fact: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, UnresolvedCode):
            raise ValueError("code must be UnresolvedCode")
        for name in ("item_id", "required_fact", "detail"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string or None")


@dataclass(frozen=True)
class PlanningEvidence:
    kind: PlanningEvidenceKind
    item_id: str | None
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PlanningEvidenceKind):
            raise ValueError("kind must be PlanningEvidenceKind")
        if self.item_id is not None and not isinstance(self.item_id, str):
            raise ValueError("item_id must be a string or None")
        if not isinstance(self.detail, str) or not self.detail:
            raise ValueError("detail must be a non-empty string")


@dataclass(frozen=True)
class ResourceRoutePlan:
    status: ResourceRouteStatus
    steps: tuple[ResourceRouteStep, ...] = ()
    unresolved: tuple[UnresolvedReason, ...] = ()
    evidence: tuple[PlanningEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "unresolved", tuple(self.unresolved))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not isinstance(self.status, ResourceRouteStatus):
            raise ValueError("status must be ResourceRouteStatus")
        _instances(self.steps, (CraftStep, TradingSessionStep), "steps")
        _instances(self.unresolved, UnresolvedReason, "unresolved")
        _instances(self.evidence, PlanningEvidence, "evidence")
        executable = self.status is ResourceRouteStatus.READY
        if executable != bool(self.steps):
            raise ValueError("only READY plans may contain executable steps")
        if self.status in {
            ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
            ResourceRouteStatus.CONTRADICTORY,
        } and not self.unresolved:
            raise ValueError("non-executable failure plans need an unresolved reason")
        if self.status in {
            ResourceRouteStatus.READY,
            ResourceRouteStatus.NO_PREREQUISITES,
        } and self.unresolved:
            raise ValueError("resolved plans cannot contain unresolved reasons")


def plan_resource_route(planning: ResourcePlanningInput) -> ResourceRoutePlan:
    """Choose visits by current numeric pressure, never by future drops."""
    if not isinstance(planning, ResourcePlanningInput):
        raise ValueError("planning must be ResourcePlanningInput")
    invalid = _validate_board(planning)
    if invalid is not None:
        return invalid
    board = planning.board
    assert isinstance(board, MonsterWaveBoardSnapshot)
    rows = {row.item_id: row for row in board.resource_rows}
    evidence = [PlanningEvidence(
        PlanningEvidenceKind.BOARD_PAIR, row.item_id,
        ("hard_pressure:red_numeric_pair" if row.balance is None else
         f"balance:{row.balance},displayed_limit:{row.displayed_limit}"),
    ) for row in board.resource_rows]
    badges = rows["brawlers_badges"]
    if badges.hard_pressure or (
        badges.balance is not None and badges.displayed_limit is not None
        and badges.balance >= badges.displayed_limit
    ):
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.WARNING, "brawlers_badges",
            "pressured_unmanaged:no_arena_route",
        ))
    for item_id, threshold in ENTRY_THRESHOLDS.items():
        row = rows[item_id]
        if row.hard_pressure or (row.balance is not None and row.balance >= threshold):
            evidence.append(PlanningEvidence(
                PlanningEvidenceKind.THRESHOLD, item_id,
                (f"hard_pressure:red>=entry:{threshold}" if row.balance is None
                 else f"balance:{row.balance}>=entry:{threshold}"),
            ))

    def at_entry(item_id: str) -> bool:
        row = rows[item_id]
        return row.hard_pressure or (row.balance is not None
                                     and row.balance >= ENTRY_THRESHOLDS[item_id])

    keys_trip = at_entry("bronze_key") or at_entry("silver_key")
    materials_trip = at_entry("weapon_material")
    hero_trip = at_entry("hero_weapon_material")
    if hero_trip:
        craft_trip = True
    elif materials_trip:
        weapon = rows["weapon_material"].balance
        hero = rows["hero_weapon_material"].balance
        # The board reader keeps these exact values whenever projection matters.
        if weapon is None or hero is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.BOARD_CONTENT_UNKNOWN,
                required_fact="exact_weapon_and_hero_for_projection",
            ),), evidence)
        craft_trip = hero + (weapon // 40) * 10 >= 800
    else:
        craft_trip = False
    if not (keys_trip or materials_trip or craft_trip):
        return ResourceRoutePlan(ResourceRouteStatus.NO_PREREQUISITES,
                                 evidence=tuple(evidence))

    # Legacy/debug facts may be supplied but cannot predict MW drops.
    conversions, problem = _unique_facts(
        planning.non_board.material_conversions, "source_item_id", MATERIAL_ITEM_IDS,
    )
    if problem is not None:
        return _contradictory(problem, evidence)
    conversion = conversions.get("weapon_material")
    if conversion is not None and (
        conversion.destination_item_id != "hero_weapon_material"
        or conversion.trading_item_id != "hero_weapon_crafting_material"
        or conversion.input_per_trade != 40
        or conversion.output_per_trade != 10
    ):
        return _insufficient((UnresolvedReason(
            UnresolvedCode.UNSUPPORTED_MATERIAL_CONVERSION, "weapon_material",
            detail="only the verified 40 Weapon -> 10 Hero conversion is supported",
        ),), evidence)
    crafts, problem = _unique_facts(
        planning.non_board.craft_capacities, "material_item_id", MATERIAL_ITEM_IDS,
    )
    if problem is not None:
        return _contradictory(problem, evidence)

    steps: list[ResourceRouteStep] = []
    if craft_trip:
        craft = crafts.get("hero_weapon_material")
        if craft is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MISSING_CRAFT_FACT, "hero_weapon_material",
                "hero_weapon_craft_recipe_and_equipment_capacity",
            ),), evidence)
        if (craft.family, craft.tier, craft.material_per_craft) != ("weapon", "hero", 49):
            return _insufficient((UnresolvedReason(
                UnresolvedCode.UNSUPPORTED_CRAFT_FACT, "hero_weapon_material",
            ),), evidence)
        if craft.free_equipment_slots is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MISSING_EQUIPMENT_CAPACITY, "hero_weapon_material",
            ),), evidence)
        if craft.free_equipment_slots < 1:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.CRAFT_ENTRY_CAPACITY_UNAVAILABLE,
                "hero_weapon_material",
            ),), evidence)
        steps.append(CraftStep("weapon", "hero"))
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.CAPABILITY, "hero_weapon_material",
            "drain_hero_until_below_49",
        ))
    if keys_trip or materials_trip:
        operations: list[TradingSessionOperation] = [KeysPromotionStep()]
        if materials_trip:
            operations.append(TradingMaterialsStep())
            evidence.append(PlanningEvidence(
                PlanningEvidenceKind.CAPABILITY, "weapon_material",
                "drain_weapon_until_below_40",
            ))
        steps.append(TradingSessionStep(tuple(operations)))
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.ORDER, None,
            "keys_first_then_materials_if_justified",
        ))
    return ResourceRoutePlan(ResourceRouteStatus.READY, steps=tuple(steps),
                             evidence=tuple(evidence))


def _validate_board(planning: ResourcePlanningInput) -> ResourceRoutePlan | None:
    board = planning.board
    if board is None:
        return _insufficient((UnresolvedReason(
            UnresolvedCode.MISSING_BOARD_SNAPSHOT,
            required_fact="MonsterWaveBoardSnapshot",
        ),), ())
    if not isinstance(board, MonsterWaveBoardSnapshot):
        return _contradictory_reason(UnresolvedReason(
            UnresolvedCode.FOREIGN_BOARD_SNAPSHOT,
            required_fact="MonsterWaveBoardSnapshot",
        ))
    if not isinstance(board.evidence, BoardEvidence):
        return _contradictory_reason(UnresolvedReason(
            UnresolvedCode.CONTRADICTORY_BOARD,
            required_fact="BoardEvidence",
        ))
    if board.evidence.observed_at > planning.now:
        return _contradictory_reason(UnresolvedReason(
            UnresolvedCode.CONTRADICTORY_BOARD,
            detail="board observation is in the future",
        ))
    if (
        board.evidence.sequence <= planning.after_sequence
        or planning.now - board.evidence.observed_at > planning.max_board_age_s
    ):
        return _insufficient((UnresolvedReason(
            UnresolvedCode.STALE_BOARD_SNAPSHOT,
            required_fact="fresh_board_snapshot",
        ),), ())
    if board.board_popup is not BoardPopup.PRESENT_WITH_ROWS:
        return _insufficient((UnresolvedReason(
            UnresolvedCode.BOARD_CONTENT_UNKNOWN,
            required_fact="board_popup_with_confirmed_rows",
        ),), ())
    rows = board.resource_rows
    if (
        not isinstance(rows, tuple)
        or len(rows) != len(BOARD_ITEM_IDS)
        or any(not isinstance(row, MonsterWaveBoardRow) for row in rows)
        or tuple(row.item_id for row in rows) != BOARD_ITEM_IDS
        or len(board.evidence.row_sequences) < 2
        or board.evidence.row_sequences[-1] != board.evidence.sequence
        or any(right <= left for left, right in zip(
            board.evidence.row_sequences, board.evidence.row_sequences[1:]
        ))
        or board.gold_key_capacity != "NOT_OBSERVABLE"
    ):
        return _contradictory_reason(UnresolvedReason(
            UnresolvedCode.CONTRADICTORY_BOARD,
            required_fact="canonical_G_board_rows_and_evidence",
        ))
    return None


def _unique_facts(items, key_name: str, allowed: tuple[str, ...] | frozenset[str]):
    result = {}
    allowed_set = frozenset(allowed)
    for item in items:
        key = getattr(item, key_name)
        if key not in allowed_set:
            return {}, f"foreign {key_name}:{key}"
        if key in result:
            return {}, f"duplicate {key_name}:{key}"
        result[key] = item
    return result, None


def _insufficient(reasons, evidence) -> ResourceRoutePlan:
    return ResourceRoutePlan(
        ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
        unresolved=tuple(reasons),
        evidence=tuple(evidence),
    )


def _contradictory(detail: str, evidence) -> ResourceRoutePlan:
    return ResourceRoutePlan(
        ResourceRouteStatus.CONTRADICTORY,
        unresolved=(UnresolvedReason(
            UnresolvedCode.CONTRADICTORY_NON_BOARD_FACTS,
            detail=detail,
        ),),
        evidence=tuple(evidence),
    )


def _contradictory_reason(reason: UnresolvedReason) -> ResourceRoutePlan:
    return ResourceRoutePlan(
        ResourceRouteStatus.CONTRADICTORY,
        unresolved=(reason,),
    )


def _instances(values, expected, name: str) -> None:
    if any(not isinstance(value, expected) for value in values):
        raise ValueError(f"{name} contains an invalid value")


def _strings(values, name: str) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) for value in result):
        raise ValueError(f"{name} must contain strings")
    return result


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _positive_int(value: object, name: str) -> int:
    result = _non_negative_int(value, name)
    if result == 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _time(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{name} must be a finite non-negative time")
    return float(value)


__all__ = (
    "CraftCapacityFact",
    "CraftStep",
    "IncomingRewardFact",
    "KeysPromotionStep",
    "MaterialConversionFact",
    "NonBoardResourceFacts",
    "PlanningEvidence",
    "PlanningEvidenceKind",
    "ResourcePlanningInput",
    "ResourceRoutePlan",
    "ResourceRouteStatus",
    "TradingMaterialOperation",
    "TradingMaterialsStep",
    "TradingSessionStep",
    "UnresolvedCode",
    "UnresolvedReason",
    "plan_resource_route",
)
