"""Evaluate the curated Daily activity semantics offline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import cv2

from bot.capture import FrameSnapshot
from bot.catalog import (
    INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
    INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    SCREEN_FRIENDS,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.perception import (
    FRIENDS_SEND_STAMINA_DAILY_SPEC,
    GUILD_ATTENDANCE_DAILY_SPEC,
    WORLD_BOSS_DAILY_SPEC,
    build_default_perception,
)
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("datasets/daily_activity_semantic_manifest.json")
DAILY_OBSERVATIONS = frozenset(
    {
        INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
        INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
        INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    }
)


@dataclass(frozen=True)
class DailyFrameResult:
    path: str
    correct: bool
    base_context: str | None
    overlays: tuple[str, ...]
    daily_observations: tuple[str, ...]


@dataclass(frozen=True)
class DailyActivitySemanticReport:
    entries: int
    correct: int
    wrong_paths: tuple[str, ...]
    friends_daily_active_frames: int
    friends_daily_inactive_frames: int
    friends_transition_verified: bool
    friends_close_to_lobby_verified: bool
    guild_daily_active_frames: int
    guild_completed_daily_absent_frames: int
    guild_actionable_daily_absent_frames: int
    world_boss_daily_active_frames: int
    world_boss_daily_inactive_frames: int
    shared_daily_asset: str
    sampled_friends_transition_upper_bound_seconds: float
    curated_friends_absence_stability_seconds: float
    frames: tuple[DailyFrameResult, ...]


def evaluate_daily_activity_semantics(
    repository_root: str | Path,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> DailyActivitySemanticReport:
    root = Path(repository_root).resolve()
    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = root / manifest
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    entries = load_manifest(manifest)
    engine = build_default_perception(root)
    resolver = build_default_resolver()

    daily_specs = (
        FRIENDS_SEND_STAMINA_DAILY_SPEC,
        GUILD_ATTENDANCE_DAILY_SPEC,
        WORLD_BOSS_DAILY_SPEC,
    )
    daily_assets = {spec.asset_path.as_posix() for spec in daily_specs}
    if len(daily_assets) != 1:
        raise ValueError("Daily activity specs must share one curated asset")

    results = []
    for sequence, entry in enumerate(entries, start=1):
        frame = cv2.imread(str(root / entry.path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(
                f"curated Daily activity frame is unreadable: {entry.path}"
            )
        batch = engine.analyze(FrameSnapshot(frame, float(sequence), sequence))
        state = resolver.resolve(batch)
        expected_base = None if entry.base_context == "unknown" else entry.base_context
        expected_status = (
            ResolutionStatus.UNKNOWN
            if expected_base is None
            else ResolutionStatus.RESOLVED
        )
        expected_daily = tuple(
            sorted(set(entry.observations) & DAILY_OBSERVATIONS)
        )
        actual_daily = tuple(
            sorted(
                item.name
                for item in batch.observations
                if item.name in DAILY_OBSERVATIONS
            )
        )
        correct = (
            state.status is expected_status
            and state.base_context == expected_base
            and state.overlays == entry.overlays
            and actual_daily == expected_daily
        )
        results.append(
            DailyFrameResult(
                path=entry.path,
                correct=correct,
                base_context=state.base_context,
                overlays=state.overlays,
                daily_observations=actual_daily,
            )
        )

    friends = [item for item in results if "/friends/" in item.path]
    transition = [item for item in friends if "/transition/" in item.path]
    guild = [item for item in results if item.base_context == SCREEN_GUILD]
    world_boss = [
        item for item in results if "/world-boss/" in item.path
    ]
    timing = payload["curation"]["friends"]["transition"]
    return DailyActivitySemanticReport(
        entries=len(entries),
        correct=sum(item.correct for item in results),
        wrong_paths=tuple(item.path for item in results if not item.correct),
        friends_daily_active_frames=sum(
            STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE in item.overlays
            for item in friends
        ),
        friends_daily_inactive_frames=sum(
            item.base_context == SCREEN_FRIENDS
            and STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE not in item.overlays
            for item in friends
        ),
        friends_transition_verified=(
            len(transition) == 3
            and STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE
            in transition[0].overlays
            and all(
                STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE not in item.overlays
                for item in transition[1:]
            )
            and all(item.correct for item in transition)
        ),
        friends_close_to_lobby_verified=any(
            item.base_context == SCREEN_LOBBY
            and "/close-lobby/" in item.path
            and item.correct
            for item in friends
        ),
        guild_daily_active_frames=sum(
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE in item.overlays
            for item in guild
        ),
        guild_completed_daily_absent_frames=sum(
            STATUS_GUILD_ATTENDANCE_COMPLETED in item.overlays
            and STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE not in item.overlays
            for item in guild
        ),
        guild_actionable_daily_absent_frames=sum(
            STATUS_GUILD_ATTENDANCE_ACTIVE in item.overlays
            and STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE not in item.overlays
            for item in guild
        ),
        world_boss_daily_active_frames=sum(
            STATUS_WORLD_BOSS_DAILY_ACTIVE in item.overlays
            for item in world_boss
        ),
        world_boss_daily_inactive_frames=sum(
            STATUS_WORLD_BOSS_DAILY_ACTIVE not in item.overlays
            for item in world_boss
        ),
        shared_daily_asset=daily_assets.pop(),
        sampled_friends_transition_upper_bound_seconds=float(
            timing["sampled_transition_upper_bound_seconds"]
        ),
        curated_friends_absence_stability_seconds=float(
            timing["curated_absence_stability_seconds"]
        ),
        frames=tuple(results),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=PROJECT_ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output", default="artifacts/daily-semantics/evaluation.json"
    )
    args = parser.parse_args(argv)
    report = evaluate_daily_activity_semantics(args.repo_root, args.manifest)
    output = Path(args.output)
    if not output.is_absolute():
        output = Path(args.repo_root).resolve() / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"entries={report.entries} correct={report.correct} "
        f"friends_transition={str(report.friends_transition_verified).lower()} "
        f"close_lobby={str(report.friends_close_to_lobby_verified).lower()} "
        f"result={'PASS' if not report.wrong_paths else 'FAIL'}"
    )
    print(f"report={output}")
    return 0 if not report.wrong_paths else 1


if __name__ == "__main__":
    raise SystemExit(main())
