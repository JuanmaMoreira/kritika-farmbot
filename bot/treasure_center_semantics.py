"""Treasure observation names; no navigation policy or cross-frame state.

Astra reconstruction (read-only ``024ff8e``) maps to these names without
copying detectors, ROIs or thresholds:

- ``SCREEN_TREASURE`` was ``screen.treasure`` with
  ``landmark.relief_treasure`` plus ``popup.relief_treasure_selector`` /
  ``popup.relief_treasure_result`` overlays;
- currency signals were ``indicator.relief_gold_key_selector`` /
  ``indicator.relief_gold_key_repeat`` (Gold) vs
  ``indicator.relief_karat_base`` / ``indicator.relief_karat_repeat``
  (premium). Gold-vs-Karat was fail-closed (``key == karat`` raises);
- no detector, template, ROI or threshold is rescued here: names only.
  Geometry and calibrations require current-pipeline HIL before any
  detector exists. The engine global is untouched in this task.
"""

SCREEN_TREASURE = "screen.treasure"

LANDMARK_TREASURE_TITLE = "landmark.treasure_title"

INDICATOR_TREASURE_GOLD_KEY_SELECTOR = "indicator.treasure_gold_key_selector"
INDICATOR_TREASURE_GOLD_KEY_REPEAT = "indicator.treasure_gold_key_repeat"
INDICATOR_TREASURE_KARAT_BASE = "indicator.treasure_karat_base"
INDICATOR_TREASURE_KARAT_REPEAT = "indicator.treasure_karat_repeat"

INDICATOR_TREASURE_SELECTOR_POPUP = "indicator.treasure_selector_popup"
INDICATOR_TREASURE_RESULT = "indicator.treasure_result"

TREASURE_OBSERVATIONS = (
    LANDMARK_TREASURE_TITLE,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_KARAT_REPEAT,
    INDICATOR_TREASURE_SELECTOR_POPUP,
    INDICATOR_TREASURE_RESULT,
)
