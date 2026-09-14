"""Generic infrastructure for scoped perception subsets.

A scope describes *what to observe* (which detectors run per frame) and
nothing else: no timeouts, no retries, no predicates, no recovery, no flow
policy, no runtime events and no embedded resolver rules.

Not-evaluated semantics are unchanged: a detector that does not run emits
no observation, so the resolver may degrade to UNKNOWN or report an
overlay as absent. Safety keeps depending on a complete ScopeSpec,
fail-fast construction and per-context equivalence tests; no tri-state
model is introduced here and ContextResolver is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import PerceptionEngine


@dataclass(frozen=True)
class ScopeSpec:
    """Immutable description of one perception detector subset."""

    name: str
    spec_names: frozenset[str]
    specialized_types: tuple[type, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        spec_names = _spec_names(self.spec_names)
        object.__setattr__(self, "spec_names", spec_names)
        specialized = _specialized_types(self.specialized_types)
        object.__setattr__(self, "specialized_types", specialized)
        if not spec_names and not specialized:
            raise ValueError("scope must select at least one detector")


def select_detectors(
    source: PerceptionEngine,
    scope: ScopeSpec,
) -> PerceptionEngine:
    """Select the detectors described by ``scope`` from ``source``.

    The subset preserves source order and reuses the same detector
    instances, so calibration, thresholds and assets are unchanged. Only
    the detector count per analyzed frame changes. Raises ``ValueError``
    when the source engine lacks any required detector instead of
    running degraded.
    """

    if not isinstance(source, PerceptionEngine):
        raise ValueError("source must be a PerceptionEngine")
    if not isinstance(scope, ScopeSpec):
        raise ValueError("scope must be a ScopeSpec")
    selected = tuple(
        detector
        for detector in source.detectors
        if getattr(getattr(detector, "spec", None), "name", None)
        in scope.spec_names
        or isinstance(detector, scope.specialized_types)
    )
    present = {
        detector.spec.name
        for detector in selected
        if getattr(getattr(detector, "spec", None), "name", None)
        in scope.spec_names
    }
    missing = set(scope.spec_names) - present
    if missing:
        raise ValueError(
            f"{scope.name} scope is missing detectors: "
            + ", ".join(sorted(missing))
        )
    for specialized in scope.specialized_types:
        if not any(isinstance(item, specialized) for item in selected):
            raise ValueError(
                f"{scope.name} scope is missing detector: "
                f"{specialized.__name__}"
            )
    return PerceptionEngine(detectors=selected)


def _spec_names(values: object) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("spec_names must be a collection of detector names")
    try:
        names = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(
            "spec_names must be a collection of detector names"
        ) from error
    if not all(isinstance(name, str) and name.strip() for name in names):
        raise ValueError("spec_names must contain only non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError("spec_names must not contain duplicates")
    return frozenset(names)


def _specialized_types(values: object) -> tuple[type, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("specialized_types must be a collection of types")
    try:
        types = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(
            "specialized_types must be a collection of types"
        ) from error
    if not all(isinstance(item, type) for item in types):
        raise ValueError("specialized_types must contain only types")
    if len(set(types)) != len(types):
        raise ValueError("specialized_types must not contain duplicates")
    return types


__all__ = (
    "ScopeSpec",
    "select_detectors",
)
