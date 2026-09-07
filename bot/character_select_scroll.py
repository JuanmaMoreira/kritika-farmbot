"""Character Select-specific profile for the reusable observed scroll."""

from __future__ import annotations

from dataclasses import dataclass

from bot.geometry import RelativeRegion
from bot.observed_scroll import ObservedScrollConfig, ViewportMotionDetector
from bot.semantic_actions import Swipe


@dataclass(frozen=True)
class CharacterSelectScrollProfile:
    """Validated viewport, gestures and policy for Character Select."""

    region: RelativeRegion = (0.4900, 0.1900, 0.8500, 0.8050)
    thumbnail_width: int = 96
    thumbnail_height: int = 72
    settled_threshold: float = 0.0500
    movement_threshold: float = 0.0300
    progress_swipe: Swipe = Swipe(
        start=(0.8000, 0.8000),
        end=(0.8000, 0.0250),
        duration_ms=190,
    )
    # Short controlled swipe for the fine phase of the sentinel search: after
    # the coarse gestures approach the list end, a full-strength swipe stops
    # producing useful positioning (live: 6 strong swipes, + card left half
    # visible). x=0.68 stays on the grid columns; 0.24 height at 250 ms aims
    # for roughly one row of travel to finish revealing a partial card.
    # Conservative values, pending live validation; never bottom evidence.
    fine_swipe: Swipe = Swipe(
        start=(0.6800, 0.6200),
        end=(0.6800, 0.3800),
        duration_ms=250,
    )
    confirmation_swipe: Swipe = Swipe(
        start=(0.6800, 0.7600),
        end=(0.6800, 0.2400),
        duration_ms=200,
    )
    required_confirmations: int = 1
    max_attempts: int = 5
    timeout: float = 6.0
    settle_for: float = 1.0

    def __post_init__(self) -> None:
        self.detector()
        self.config()

    def detector(self) -> ViewportMotionDetector:
        return ViewportMotionDetector(
            region=self.region,
            thumbnail_width=self.thumbnail_width,
            thumbnail_height=self.thumbnail_height,
            unchanged_threshold=self.settled_threshold,
        )

    def config(self) -> ObservedScrollConfig:
        return ObservedScrollConfig(
            progress_swipe=self.progress_swipe,
            confirmation_swipe=self.confirmation_swipe,
            movement_threshold=self.movement_threshold,
            required_confirmations=self.required_confirmations,
            max_attempts=self.max_attempts,
            timeout=self.timeout,
            settle_for=self.settle_for,
            abort_on_ineffective=False,
        )


DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE = CharacterSelectScrollProfile()


__all__ = (
    "CharacterSelectScrollProfile",
    "DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE",
)
