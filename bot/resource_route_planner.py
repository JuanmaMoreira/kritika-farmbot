"""Pure deterministic planning for Monster Wave resource prerequisites.

The board owns description only.  This module combines that immutable
description with explicitly supplied non-board facts and returns symbolic
capability steps.  It performs no observation, navigation or execution.

The Monster Wave pair semantics are deliberately narrow: ``balance`` is the
currently displayed balance and ``displayed_limit`` is the displayed limit.
Neither value is an incoming reward, recipe or Trading ``have/need`` pair.
Consequently an overflow is actionable only when an exact incoming reward
amount is supplied separately and ``balance + incoming > displayed_limit``.
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
    quantity: int

    def __post_init__(self) -> None:
        for name in ("trading_item_id", "source_item_id", "destination_item_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        _positive_int(self.quantity, "quantity")


@dataclass(frozen=True)
class TradingMaterialsStep:
    operations: tuple[TradingMaterialOperation, ...]
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
    quantity: int
    capability: str = "craft"

    def __post_init__(self) -> None:
        if not isinstance(self.family, str) or not self.family:
            raise ValueError("family must be a non-empty string")
        if not isinstance(self.tier, str) or not self.tier:
            raise ValueError("tier must be a non-empty string")
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
    """Return one deterministic, fail-closed prerequisite plan."""

    if not isinstance(planning, ResourcePlanningInput):
        raise ValueError("planning must be ResourcePlanningInput")
    invalid = _validate_board(planning)
    if invalid is not None:
        return invalid
    board = planning.board
    assert isinstance(board, MonsterWaveBoardSnapshot)
    rows = {row.item_id: row for row in board.resource_rows}
    evidence = [
        PlanningEvidence(
            PlanningEvidenceKind.BOARD_PAIR,
            row.item_id,
            f"balance:{row.balance},displayed_limit:{row.displayed_limit}",
        )
        for row in board.resource_rows
    ]

    rewards, problem = _unique_facts(
        planning.non_board.incoming_rewards, "item_id", BOARD_ITEM_IDS,
    )
    if problem is not None:
        return _contradictory(problem, evidence)
    missing = tuple(
        UnresolvedReason(
            UnresolvedCode.MISSING_INCOMING_REWARD,
            item_id,
            f"incoming_reward:{item_id}",
            "exact incoming amount is required; zero must be explicit",
        )
        for item_id in BOARD_ITEM_IDS
        if item_id not in rewards or rewards[item_id].amount is None
    )
    if missing:
        return _insufficient(missing, evidence)

    overflow: dict[str, int] = {}
    for item_id in BOARD_ITEM_IDS:
        row = rows[item_id]
        reward = rewards[item_id]
        assert isinstance(reward, IncomingRewardFact) and reward.amount is not None
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.INCOMING_REWARD,
            item_id,
            f"exact:{reward.amount}",
        ))
        if reward.amount > 0 and row.balance + reward.amount > row.displayed_limit:
            overflow[item_id] = row.balance + reward.amount - row.displayed_limit
            evidence.append(PlanningEvidence(
                PlanningEvidenceKind.OVERFLOW,
                item_id,
                f"{row.balance}+{reward.amount}>{row.displayed_limit}",
            ))

    if not overflow:
        return ResourceRoutePlan(
            ResourceRouteStatus.NO_PREREQUISITES,
            evidence=tuple(evidence),
        )
    if "brawlers_badges" in overflow:
        return _insufficient((UnresolvedReason(
            UnresolvedCode.ARENA_TICKET_ROUTE_NOT_ESTABLISHED,
            "brawlers_badges",
            "arena_ticket_row_and_conversion",
            "G did not establish Arena Ticket as a distinct planner fact",
        ),), evidence)

    keys_needed = bool(KEY_ITEM_IDS.intersection(overflow))
    conversion_step: TradingMaterialsStep | None = None
    craft_step: CraftStep | None = None

    conversions, problem = _unique_facts(
        planning.non_board.material_conversions, "source_item_id", MATERIAL_ITEM_IDS,
    )
    if problem is not None:
        return _contradictory(problem, evidence)
    crafts, problem = _unique_facts(
        planning.non_board.craft_capacities, "material_item_id", MATERIAL_ITEM_IDS,
    )
    if problem is not None:
        return _contradictory(problem, evidence)

    trade_count = 0
    conversion = None
    if "weapon_material" in overflow:
        conversion = conversions.get("weapon_material")
        if conversion is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MISSING_MATERIAL_CONVERSION,
                "weapon_material",
                "material_conversion:weapon_material",
                "a visible row does not identify its Trading conversion",
            ),), evidence)
        assert isinstance(conversion, MaterialConversionFact)
        if (
            conversion.destination_item_id != "hero_weapon_material"
            or conversion.trading_item_id != "hero_weapon_crafting_material"
        ):
            return _insufficient((UnresolvedReason(
                UnresolvedCode.UNSUPPORTED_MATERIAL_CONVERSION,
                "weapon_material",
                "weapon_to_hero_weapon_conversion",
                "only the closed Weapon -> Hero Weapon Trading row is supported",
            ),), evidence)
        trade_count = math.ceil(
            overflow["weapon_material"] / conversion.input_per_trade
        )
        if rows["weapon_material"].balance < trade_count * conversion.input_per_trade:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MATERIAL_CONVERSION_NOT_ACTIONABLE,
                "weapon_material",
                "current_material_for_conversion",
                "incoming rewards cannot be consumed before they arrive",
            ),), evidence)

    hero_reward = rewards["hero_weapon_material"]
    assert isinstance(hero_reward, IncomingRewardFact) and hero_reward.amount is not None
    projected_hero = rows["hero_weapon_material"].balance + hero_reward.amount
    if conversion is not None:
        projected_hero += trade_count * conversion.output_per_trade
    craft_needed = projected_hero > rows["hero_weapon_material"].displayed_limit
    if craft_needed:
        craft = crafts.get("hero_weapon_material")
        if craft is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MISSING_CRAFT_FACT,
                "hero_weapon_material",
                "hero_weapon_craft_recipe_and_equipment_capacity",
                "target tier, recipe and Equipment capacity are non-board facts",
            ),), evidence)
        assert isinstance(craft, CraftCapacityFact)
        if craft.family != "weapon" or craft.tier != "hero":
            return _insufficient((UnresolvedReason(
                UnresolvedCode.UNSUPPORTED_CRAFT_FACT,
                "hero_weapon_material",
                "hero_weapon_craft_recipe",
                "Craft standalone is closed only for an explicit Hero recipe",
            ),), evidence)
        if craft.free_equipment_slots is None:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MISSING_EQUIPMENT_CAPACITY,
                "hero_weapon_material",
                "free_equipment_slots",
                "Craft requires at least one free Equipment slot on entry",
            ),), evidence)
        if craft.free_equipment_slots < 1:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.CRAFT_ENTRY_CAPACITY_UNAVAILABLE,
                "hero_weapon_material",
                "free_equipment_slots>=1",
                "Equipment Relief is reactive and is not a planner step",
            ),), evidence)
        craft_count = math.ceil(
            (projected_hero - rows["hero_weapon_material"].displayed_limit)
            / craft.material_per_craft
        )
        if craft_count != 1:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.MULTI_CRAFT_POLICY_NOT_ESTABLISHED,
                "hero_weapon_material",
                "multi_craft_route_policy",
                "the closed Craft capability proves one request, not planner repetition",
            ),), evidence)
        if rows["hero_weapon_material"].balance < craft.material_per_craft:
            return _insufficient((UnresolvedReason(
                UnresolvedCode.CRAFT_MATERIAL_UNAVAILABLE,
                "hero_weapon_material",
                "current_hero_weapon_material",
                "craft-first cannot spend incoming or post-Trade material",
            ),), evidence)
        craft_step = CraftStep(craft.family, craft.tier, 1)
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.CAPABILITY,
            "hero_weapon_material",
            "craft:weapon:hero:one",
        ))

    if conversion is not None:
        conversion_step = TradingMaterialsStep((TradingMaterialOperation(
            conversion.trading_item_id,
            conversion.source_item_id,
            conversion.destination_item_id,
            trade_count,
        ),))
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.CAPABILITY,
            "weapon_material",
            f"trading_materials:{conversion.trading_item_id}:exact:{trade_count}",
        ))

    trading_operations: list[TradingSessionOperation] = []
    if keys_needed:
        trading_operations.append(KeysPromotionStep())
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.CAPABILITY,
            "keys",
            "keys_promotion:C6a/C6b-owned",
        ))
    if conversion_step is not None:
        trading_operations.append(conversion_step)
    if len(trading_operations) == 2:
        evidence.append(PlanningEvidence(
            PlanningEvidenceKind.ORDER,
            None,
            "one_trading_visit:keys_then_materials; Trading opens in Avatar & Keys",
        ))

    steps: list[ResourceRouteStep] = []
    if craft_step is not None:
        steps.append(craft_step)
    if trading_operations:
        steps.append(TradingSessionStep(tuple(trading_operations)))
    if not steps:
        # Defensive: all recognized overflows must either produce a step or an
        # unresolved return above.
        return _contradictory("recognized overflow produced no capability", evidence)
    return ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=tuple(steps),
        evidence=tuple(evidence),
    )


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
