"""Human acquisition labels kept outside the production semantic catalog.

The Perception Workbench uses this vocabulary to label raw observational
evidence.  Candidate labels are deliberately inert: importing this module does
not add rules to :mod:`bot.catalog` or make a label resolvable in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from bot.observations import validate_semantic_name


class AcquisitionLabelOrigin(str, Enum):
    PRODUCTION = "production"
    CANDIDATE = "candidate"


@dataclass(frozen=True)
class AcquisitionLabel:
    name: str
    origin: AcquisitionLabelOrigin

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))


@dataclass(frozen=True)
class AcquisitionVocabulary:
    """Explicit base/overlay choices available to a human annotator."""

    bases: tuple[AcquisitionLabel, ...]
    overlays: tuple[AcquisitionLabel, ...]

    def __post_init__(self) -> None:
        _validate_labels(self.bases, prefix="screen.")
        _validate_labels(self.overlays, prefix="popup.")

    @property
    def base_names(self) -> tuple[str, ...]:
        return tuple(label.name for label in self.bases)

    @property
    def overlay_names(self) -> tuple[str, ...]:
        return tuple(label.name for label in self.overlays)

    def origin_for(self, name: str) -> AcquisitionLabelOrigin:
        for label in (*self.bases, *self.overlays):
            if label.name == name:
                return label.origin
        raise KeyError(name)


# A deliberately small current-season acquisition seed.  These names are raw
# annotation choices, not ContextRule/OverlayRule declarations.
DEFAULT_CANDIDATE_BASE_LABELS = (
    "screen.guild_shop",
    "screen.inventory",
)
DEFAULT_CANDIDATE_OVERLAY_LABELS = (
    "popup.bag_full_alert",
)


def build_acquisition_vocabulary(
    *,
    production_base_labels: Iterable[str] = (),
    production_overlay_labels: Iterable[str] = (),
    candidate_base_labels: Iterable[str] = DEFAULT_CANDIDATE_BASE_LABELS,
    candidate_overlay_labels: Iterable[str] = DEFAULT_CANDIDATE_OVERLAY_LABELS,
) -> AcquisitionVocabulary:
    """Merge explicit production names and acquisition-only candidates.

    Production names win if a name appears in both inputs.  The function knows
    nothing about ContextRule or ContextResolver and performs no registration.
    """

    return AcquisitionVocabulary(
        bases=_merge_labels(production_base_labels, candidate_base_labels),
        overlays=_merge_labels(production_overlay_labels, candidate_overlay_labels),
    )


def _merge_labels(
    production: Iterable[str],
    candidates: Iterable[str],
) -> tuple[AcquisitionLabel, ...]:
    result: list[AcquisitionLabel] = []
    seen: set[str] = set()
    for origin, names in (
        (AcquisitionLabelOrigin.PRODUCTION, production),
        (AcquisitionLabelOrigin.CANDIDATE, candidates),
    ):
        for name in names:
            name = validate_semantic_name(name)
            if name in seen:
                continue
            seen.add(name)
            result.append(AcquisitionLabel(name, origin))
    return tuple(result)


def _validate_labels(
    labels: tuple[AcquisitionLabel, ...],
    *,
    prefix: str,
) -> None:
    names = tuple(label.name for label in labels)
    if len(names) != len(set(names)):
        raise ValueError("acquisition labels must be unique within each kind")
    if any(not name.startswith(prefix) for name in names):
        raise ValueError(f"acquisition labels must use the {prefix!r} namespace")
