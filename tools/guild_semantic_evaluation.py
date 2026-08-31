"""Evaluate curated Guild semantics and navigation evidence offline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import cv2

from bot.capture import FrameSnapshot
from bot.catalog import (
    INDICATOR_GUILD_ATTENDANCE_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_COMPLETED,
    MENU_QUICK,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    build_default_resolver,
)
from bot.perception import GuildAttendanceDetector, build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("datasets/guild_semantic_manifest.json")


@dataclass(frozen=True)
class GuildFrameResult:
    path: str
    correct: bool
    status: str
    base_context: str | None
    overlays: tuple[str, ...]
    observations: tuple[str, ...]
    attendance_value_mean: float


@dataclass(frozen=True)
class GuildSemanticReport:
    entries: int
    correct: int
    wrong_paths: tuple[str, ...]
    active_value_min: float
    active_value_max: float
    completed_value_min: float
    completed_value_max: float
    transition_upper_bound_seconds: float
    completed_bubble_frames: int
    completed_bubble_frames_correct: int
    quick_menu_from_guild_frames: int
    quick_menu_from_guild_frames_correct: int
    lobby_quick_menu_guild_route_confirmed: bool
    frames: tuple[GuildFrameResult, ...]


def evaluate_guild_semantics(
    repository_root: str | Path,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> GuildSemanticReport:
    root = Path(repository_root).resolve()
    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = root / manifest
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    entries = load_manifest(manifest)
    engine = build_default_perception(root)
    resolver = build_default_resolver()
    attendance = next(
        detector
        for detector in engine.detectors
        if isinstance(detector, GuildAttendanceDetector)
    )

    results = []
    active_values = []
    completed_values = []
    bubble_total = bubble_correct = 0
    quick_total = quick_correct = 0
    for sequence, entry in enumerate(entries, start=1):
        frame = cv2.imread(str(root / entry.path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"curated Guild frame is unreadable: {entry.path}")
        batch = engine.analyze(FrameSnapshot(frame, float(sequence), sequence))
        state = resolver.resolve(batch)
        observation_names = tuple(sorted(item.name for item in batch.observations))
        expected_status = (
            ResolutionStatus.UNKNOWN
            if entry.base_context == "unknown"
            else ResolutionStatus.RESOLVED
        )
        expected_base = None if entry.base_context == "unknown" else entry.base_context
        correct = (
            state.status is expected_status
            and state.base_context == expected_base
            and state.overlays == entry.overlays
            and not (
                INDICATOR_GUILD_ATTENDANCE_ACTIVE in observation_names
                and INDICATOR_GUILD_ATTENDANCE_COMPLETED in observation_names
            )
        )
        reading = attendance.measure(frame)
        if INDICATOR_GUILD_ATTENDANCE_ACTIVE in entry.observations:
            active_values.append(reading.value_mean)
        if INDICATOR_GUILD_ATTENDANCE_COMPLETED in entry.observations:
            completed_values.append(reading.value_mean)
        if "completed-bubble" in entry.path:
            bubble_total += 1
            bubble_correct += int(
                correct and STATUS_GUILD_ATTENDANCE_COMPLETED in state.overlays
            )
        if "/quick-menu-from-guild/" in entry.path:
            quick_total += 1
            quick_correct += int(
                correct
                and state.base_context == SCREEN_GUILD
                and state.overlays == (MENU_QUICK,)
            )
        results.append(
            GuildFrameResult(
                path=entry.path,
                correct=correct,
                status=state.status.value,
                base_context=state.base_context,
                overlays=state.overlays,
                observations=observation_names,
                attendance_value_mean=reading.value_mean,
            )
        )

    paths = {entry.path for entry in entries}
    route_confirmed = (
        any("/lobby-route/" in path for path in paths)
        and any("/quick-menu-from-lobby/" in path for path in paths)
        and any("/after-quick-menu/" in path for path in paths)
        and all(result.correct for result in results)
        and any(
            result.base_context == SCREEN_LOBBY
            for result in results
            if "/lobby-route/" in result.path
        )
        and any(
            result.base_context == SCREEN_GUILD
            for result in results
            if "/after-quick-menu/" in result.path
        )
    )
    transition = payload["curation"]["attendance_transition"]
    return GuildSemanticReport(
        entries=len(entries),
        correct=sum(result.correct for result in results),
        wrong_paths=tuple(result.path for result in results if not result.correct),
        active_value_min=min(active_values),
        active_value_max=max(active_values),
        completed_value_min=min(completed_values),
        completed_value_max=max(completed_values),
        transition_upper_bound_seconds=float(
            transition["curated_transition_upper_bound_seconds"]
        ),
        completed_bubble_frames=bubble_total,
        completed_bubble_frames_correct=bubble_correct,
        quick_menu_from_guild_frames=quick_total,
        quick_menu_from_guild_frames_correct=quick_correct,
        lobby_quick_menu_guild_route_confirmed=route_confirmed,
        frames=tuple(results),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=PROJECT_ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output", default="artifacts/guild-semantic/evaluation.json"
    )
    args = parser.parse_args(argv)
    report = evaluate_guild_semantics(args.repo_root, args.manifest)
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
        f"route={str(report.lobby_quick_menu_guild_route_confirmed).lower()} "
        f"result={'PASS' if not report.wrong_paths else 'FAIL'}"
    )
    print(f"report={output}")
    return 0 if not report.wrong_paths else 1


if __name__ == "__main__":
    raise SystemExit(main())
