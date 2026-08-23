"""Pure deterministic resolution of semantic observations into UI state."""

from __future__ import annotations

from dataclasses import dataclass

from bot.observations import (
    Observation,
    ObservationBatch,
    normalize_confidence,
    validate_semantic_name,
)
from bot.state import ResolutionStatus, ResolvedState


@dataclass(frozen=True)
class ContextRule:
    """Evidence required to identify one base context or overlay."""

    name: str
    requires: tuple[str, ...]
    min_confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        requirements = _requirements(self.requires)
        object.__setattr__(self, "requires", tuple(sorted(requirements)))
        object.__setattr__(
            self,
            "min_confidence",
            normalize_confidence(self.min_confidence),
        )


@dataclass(frozen=True)
class RuleMatch:
    """Selected evidence explaining why one rule matched a batch."""

    rule: ContextRule
    evidence: tuple[Observation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rule, ContextRule):
            raise ValueError("rule must be a ContextRule")
        evidence = tuple(self.evidence)
        if not all(isinstance(item, Observation) for item in evidence):
            raise ValueError("evidence must contain only Observation instances")
        if tuple(item.name for item in evidence) != self.rule.requires:
            raise ValueError("evidence must satisfy each rule requirement exactly once")
        if any(
            item.confidence < self.rule.min_confidence for item in evidence
        ):
            raise ValueError("evidence must satisfy the rule confidence threshold")
        object.__setattr__(self, "evidence", evidence)

    @property
    def confidence(self) -> float:
        """Conservative match confidence: the weakest selected requirement."""

        return min(item.confidence for item in self.evidence)


@dataclass(frozen=True)
class ContextResolver:
    """Resolve one batch using explicitly injected base and overlay rules."""

    base_rules: tuple[ContextRule, ...] = ()
    overlay_rules: tuple[ContextRule, ...] = ()

    def __post_init__(self) -> None:
        base_rules = _rules(self.base_rules, "base_rules")
        overlay_rules = _rules(self.overlay_rules, "overlay_rules")
        _reject_duplicate_rule_names(base_rules, "base_rules")
        _reject_duplicate_rule_names(overlay_rules, "overlay_rules")
        object.__setattr__(
            self, "base_rules", tuple(sorted(base_rules, key=lambda rule: rule.name))
        )
        object.__setattr__(
            self,
            "overlay_rules",
            tuple(sorted(overlay_rules, key=lambda rule: rule.name)),
        )

    def resolve(self, batch: ObservationBatch) -> ResolvedState:
        """Resolve base context and overlays without IO or temporal state."""

        if not isinstance(batch, ObservationBatch):
            raise ValueError("batch must be an ObservationBatch")

        base_matches = self.matching_base_rules(batch)
        overlay_matches = self.matching_overlay_rules(batch)
        base_candidates = tuple(match.rule.name for match in base_matches)
        overlays = tuple(match.rule.name for match in overlay_matches)

        if not base_candidates:
            status = ResolutionStatus.UNKNOWN
            base_context = None
            ambiguous_candidates: tuple[str, ...] = ()
        elif len(base_candidates) == 1:
            status = ResolutionStatus.RESOLVED
            base_context = base_candidates[0]
            ambiguous_candidates = ()
        else:
            status = ResolutionStatus.AMBIGUOUS
            base_context = None
            ambiguous_candidates = base_candidates

        return ResolvedState(
            status=status,
            sequence=batch.sequence,
            timestamp=batch.timestamp,
            base_context=base_context,
            overlays=overlays,
            subcontext=None,
            base_candidates=ambiguous_candidates,
        )

    def matching_base_rules(
        self, batch: ObservationBatch
    ) -> tuple[RuleMatch, ...]:
        """Return deterministic diagnostics for matching base rules."""

        return _matching_rules(self.base_rules, batch)

    def matching_overlay_rules(
        self, batch: ObservationBatch
    ) -> tuple[RuleMatch, ...]:
        """Return deterministic diagnostics for matching overlay rules."""

        return _matching_rules(self.overlay_rules, batch)


def match_rule(rule: ContextRule, batch: ObservationBatch) -> RuleMatch | None:
    """Match a rule using the highest-confidence observation per requirement.

    Confidence values are compared directly to the inclusive rule threshold.
    They are never summed, averaged, or weighted according to source.
    """

    if not isinstance(rule, ContextRule):
        raise ValueError("rule must be a ContextRule")
    if not isinstance(batch, ObservationBatch):
        raise ValueError("batch must be an ObservationBatch")

    evidence: list[Observation] = []
    for requirement in rule.requires:
        selected = batch.best(requirement)
        if selected is None or selected.confidence < rule.min_confidence:
            return None
        evidence.append(selected)
    return RuleMatch(rule=rule, evidence=tuple(evidence))


def _requirements(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("requires must be a collection of semantic names")
    try:
        requirements = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("requires must be a collection of semantic names") from error
    if not requirements:
        raise ValueError("requires must not be empty")
    try:
        validated = tuple(validate_semantic_name(value) for value in requirements)
    except ValueError as error:
        raise ValueError("requires must contain semantic names") from error
    if len(set(validated)) != len(validated):
        raise ValueError("requires must not contain duplicates")
    return validated


def _rules(values: object, field: str) -> tuple[ContextRule, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field} must be a collection of ContextRule instances")
    try:
        rules = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(
            f"{field} must be a collection of ContextRule instances"
        ) from error
    if not all(isinstance(rule, ContextRule) for rule in rules):
        raise ValueError(f"{field} must contain only ContextRule instances")
    return rules


def _reject_duplicate_rule_names(
    rules: tuple[ContextRule, ...], field: str
) -> None:
    names = tuple(rule.name for rule in rules)
    duplicates = sorted(name for name in set(names) if names.count(name) > 1)
    if duplicates:
        raise ValueError(f"{field} contains duplicate rule names: {duplicates!r}")


def _matching_rules(
    rules: tuple[ContextRule, ...], batch: ObservationBatch
) -> tuple[RuleMatch, ...]:
    if not isinstance(batch, ObservationBatch):
        raise ValueError("batch must be an ObservationBatch")
    return tuple(
        match
        for rule in rules
        if (match := match_rule(rule, batch)) is not None
    )
