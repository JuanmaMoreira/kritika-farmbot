"""MW landmark calibration over the curated global corpus (see MW design doc)."""
from pathlib import Path
from bot.perception.specs import LocalCvSpec, LinearGapCalibration

MONSTER_WAVE_SPECS = (
    LocalCvSpec(
        'landmark.monster_wave_weekly_results', Path('assets/ui/landmarks/monster-wave/monster_wave_weekly_results.png'),
        (.312, .689, .690, .763),
        LinearGapCalibration(0.3925202190876007, 0.9811031222343445),
    ),
    LocalCvSpec(
        'landmark.monster_wave_title', Path('assets/ui/landmarks/monster-wave/monster_wave_title.png'),
        (0.16799999999999998, 0.115, 0.27, 0.187),
        LinearGapCalibration(0.4018985331058502, 0.9582358598709106),
    ),
    LocalCvSpec(
        'indicator.monster_wave_needs_tickets', Path('assets/ui/landmarks/monster-wave/monster_wave_needs_tickets.png'),
        (0.704, 0.659, 0.829, 0.759),
        LinearGapCalibration(0.8012882471084595, 0.9738719463348389),
    ),
    LocalCvSpec(
        'indicator.monster_wave_ready', Path('assets/ui/landmarks/monster-wave/monster_wave_ready.png'),
        (0.649, 0.659, 0.829, 0.759),
        LinearGapCalibration(0.7003953456878662, 0.9248269200325012),
    ),
    LocalCvSpec(
        'indicator.monster_wave_time_remaining', Path('assets/ui/landmarks/monster-wave/monster_wave_time_remaining.png'),
        (0.545, 0.66, 0.664, 0.72),
        LinearGapCalibration(0.34072840213775635, 0.9667404294013977),
    ),
    LocalCvSpec(
        'landmark.monster_wave_skip_process', Path('assets/ui/landmarks/monster-wave/monster_wave_skip_process.png'),
        (0.704, 0.666, 0.829, 0.748),
        LinearGapCalibration(0.28309935331344604, 0.9698683023452759),
    ),
    LocalCvSpec(
        'indicator.monster_wave_max_selected', Path('assets/ui/landmarks/monster-wave/monster_wave_max_selected.png'),
        (0.756, 0.541, 0.828, 0.636),
        LinearGapCalibration(0.5779778957366943, 0.9405034184455872),
    ),
    LocalCvSpec(
        'landmark.monster_wave_usage_unobstructed', Path('assets/ui/landmarks/monster-wave/monster_wave_usage_unobstructed.png'),
        (0.646, 0.5519999999999999, 0.768, 0.639),
        LinearGapCalibration(0.31456470489501953, 0.9854122996330261),
    ),
    LocalCvSpec(
        'landmark.monster_wave_usage_tooltip', Path('assets/ui/landmarks/monster-wave/monster_wave_usage_tooltip.png'),
        (0.596, 0.523, 0.843, 0.675),
        LinearGapCalibration(0.2204531878232956, 0.9774290919303894),
    ),
    LocalCvSpec(
        'landmark.monster_wave_ticket_purchase', Path('assets/ui/landmarks/monster-wave/monster_wave_ticket_purchase.png'),
        (0.357, 0.069, 0.64, 0.14100000000000001),
        LinearGapCalibration(0.3052881360054016, 0.9942125082015991),
    ),
    LocalCvSpec(
        'indicator.monster_wave_purchase_full', Path('assets/ui/landmarks/monster-wave/monster_wave_purchase_full.png'),
        (0.546, 0.633, 0.62, 0.6990000000000001),
        LinearGapCalibration(0.9313202500343323, 0.96092689037323),
    ),
    LocalCvSpec(
        'landmark.monster_wave_insufficient_sapphires', Path('assets/ui/landmarks/monster-wave/monster_wave_insufficient_sapphires.png'),
        (0.349, 0.422, 0.649, 0.524),
        LinearGapCalibration(0.5263652205467224, 0.9855585694313049),
    ),
    LocalCvSpec(
        'landmark.monster_wave_inventory_board', Path('assets/ui/landmarks/monster-wave/monster_wave_inventory_board.png'),
        (0.347, 0.493, 0.655, 0.5730000000000001),
        LinearGapCalibration(0.42359694838523865, 0.9795508980751038),
    ),
    LocalCvSpec(
        'landmark.monster_wave_clear', Path('assets/ui/landmarks/monster-wave/monster_wave_clear.png'),
        (0.374, 0.135, 0.626, 0.261),
        LinearGapCalibration(0.27848151326179504, 0.9977714419364929),
    ),
    LocalCvSpec(
        'indicator.monster_wave_daily_active', Path('assets/ui/landmarks/monster-wave/monster_wave_daily_active.png'),
        (0.149, 0.192, 0.199, 0.281),
        LinearGapCalibration(0.3963564932346344, 0.984770655632019),
    ),
    LocalCvSpec(
        'landmark.monster_wave_new_ranking', Path('assets/ui/landmarks/monster-wave/monster_wave_new_ranking.png'),
        (0.419, 0.15100000000000002, 0.58, 0.235),
        LinearGapCalibration(0.5560694336891174, 0.9936479330062866),
    ),
)
