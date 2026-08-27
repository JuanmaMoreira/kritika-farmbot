from bot.acquisition_vocabulary import (
    AcquisitionLabelOrigin,
    DEFAULT_CANDIDATE_BASE_LABELS,
    DEFAULT_CANDIDATE_OVERLAY_LABELS,
    build_acquisition_vocabulary,
)
from bot.catalog import MENU_QUICK, POPUP_INVENTORY_FULL, build_default_resolver


def test_acquisition_candidates_are_separate_from_production_rules():
    resolver = build_default_resolver()
    production_bases = tuple(rule.name for rule in resolver.base_rules)
    production_overlays = tuple(rule.name for rule in resolver.overlay_rules)

    vocabulary = build_acquisition_vocabulary(
        production_base_labels=production_bases,
        production_overlay_labels=production_overlays,
    )

    assert set(production_bases).issubset(vocabulary.base_names)
    assert set(production_overlays).issubset(vocabulary.overlay_names)
    assert set(DEFAULT_CANDIDATE_BASE_LABELS).isdisjoint(production_bases)
    assert set(DEFAULT_CANDIDATE_OVERLAY_LABELS).isdisjoint(production_overlays)
    assert vocabulary.origin_for("screen.guild_shop") is AcquisitionLabelOrigin.CANDIDATE
    assert vocabulary.origin_for(production_bases[0]) is AcquisitionLabelOrigin.PRODUCTION


def test_candidate_bases_are_valid_human_choices_without_rules():
    vocabulary = build_acquisition_vocabulary()

    assert "screen.guild_shop" in vocabulary.base_names
    assert vocabulary.overlay_names == ()
    assert MENU_QUICK not in vocabulary.overlay_names


def test_promoted_quick_menu_is_exposed_as_production():
    resolver = build_default_resolver()
    vocabulary = build_acquisition_vocabulary(
        production_base_labels=(rule.name for rule in resolver.base_rules),
        production_overlay_labels=(rule.name for rule in resolver.overlay_rules),
    )

    assert vocabulary.origin_for(MENU_QUICK) is AcquisitionLabelOrigin.PRODUCTION
    assert (
        vocabulary.origin_for(POPUP_INVENTORY_FULL)
        is AcquisitionLabelOrigin.PRODUCTION
    )


def test_production_name_wins_if_a_candidate_list_repeats_it():
    vocabulary = build_acquisition_vocabulary(
        production_base_labels=("screen.lobby",),
        candidate_base_labels=("screen.lobby", "screen.guild_shop"),
    )

    assert vocabulary.base_names == ("screen.lobby", "screen.guild_shop")
    assert vocabulary.origin_for("screen.lobby") is AcquisitionLabelOrigin.PRODUCTION
