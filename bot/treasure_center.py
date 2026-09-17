"""Treasure context and Gold Keys readiness over snapshots.

Pure predicates in the Trading C1 idiom: no navigation, no input, no
policy beyond refusing to authorize motion on anything but positively
demonstrated content. Readiness is Treasure chrome plus a positive Gold
Keys signal on the same snapshot; Treasure chrome alone never authorizes
an open. Entry actions and detectors arrive with HIL evidence; this
module only decides what observations mean.

No scroll lives here and no Equipment/Trading state is consulted:
Equipment full never blocks Treasure and Trading output-full is never
read here (separation is tested in ``tests/test_treasure_keys.py``).
"""

from __future__ import annotations

from bot.catalog import SEMANTIC_CONFIDENCE_THRESHOLD
from bot.state import ResolutionStatus
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_KARAT_REPEAT,
    SCREEN_TREASURE,
)


def has(snapshot, *names) -> bool:
    present = {
        observation.name
        for observation in snapshot.observations.observations
        if observation.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD
    }
    return set(names) <= present


def is_treasure_screen(snapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_TREASURE
    )


def clean_treasure(snapshot) -> bool:
    return is_treasure_screen(snapshot) and not snapshot.state.overlays


def has_gold_signal(snapshot) -> bool:
    return has(snapshot, INDICATOR_TREASURE_GOLD_KEY_SELECTOR) or has(
        snapshot, INDICATOR_TREASURE_GOLD_KEY_REPEAT
    )


def has_karat_signal(snapshot) -> bool:
    return has(snapshot, INDICATOR_TREASURE_KARAT_BASE) or has(
        snapshot, INDICATOR_TREASURE_KARAT_REPEAT
    )


def is_gold_keys_content_ready(snapshot) -> bool:
    """Treasure with positively demonstrated Gold Keys content.

    Requires clean Treasure plus at least one Gold signal. A Karat
    signal alongside Gold is contradictory chrome here (Astra
    ``key == karat`` fail-closed): readiness is False so no input is
    authorized on the snapshot. Karat-only (no Gold) is simply not
    ready; the per-action fresh currency fact (``bot.treasure_keys``)
    distinguishes NO_KEYS from PREMIUM_CURRENCY_BOUNDARY.
    """
    return (
        clean_treasure(snapshot)
        and has_gold_signal(snapshot)
        and not has_karat_signal(snapshot)
    )


__all__ = (
    "clean_treasure",
    "has",
    "has_gold_signal",
    "has_karat_signal",
    "is_gold_keys_content_ready",
    "is_treasure_screen",
)
