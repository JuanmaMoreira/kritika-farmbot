"""Curate Workbench evidence and evaluate production perception offline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
from statistics import median
from typing import Iterable

import cv2

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    INDICATOR_COMBINE_ROW_BOTTOM,
    INDICATOR_COMBINE_ROWS,
    INDICATOR_COMBINE_ROWS_UPPER,
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_COMBINE_ALL_TITLE,
    LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE,
    LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE,
    LANDMARK_COMBINE_FUSE_ACTIVE,
    LANDMARK_COMBINE_FUSE_TAB,
    LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_SOCKET_ENHANCE_ALL_TITLE,
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    LANDMARK_SOCKET_INVENTORY_FULL_PROMPT,
    LANDMARK_SOCKET_NO_MATERIAL_PROMPT,
    LANDMARK_SOCKET_SELL_BULK_BUTTON,
    LANDMARK_SOCKET_TAB,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    MENU_QUICK,
    MODE_COMBINE_FUSE,
    MODE_COMBINE_TRANSMUTE,
    OVERLAY_WORLD_BOSS_RAID_COMPLETE,
    OVERLAY_WORLD_BOSS_SELECT_BOSS,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_INVENTORY_FULL,
    POPUP_PURCHASE_CONFIRMATION,
    POPUP_SOCKET_ENHANCE_ALL,
    POPUP_SOCKET_INVENTORY_FULL,
    POPUP_SOCKET_NO_MATERIAL,
    POPUP_SOCKET_SELL,
    POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
    POPUP_EQUIPMENT_INVENTORY_FULL,
    PANEL_COMBINE_AWAKENED_TRANSMUTE,
    PANEL_COMBINE_ETHEREAL_RANDOM_PART,
    POPUP_COMBINE_ALL,
    POPUP_ETHEREAL_MASS_COMBINE,
    POPUP_ETHEREAL_NO_MATERIAL,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_BLACK_MARKET,
    SCREEN_CHARACTER_SELECT,
    SCREEN_COMBINE,
    SCREEN_LOBBY,
    SCREEN_SOCKET,
    SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE,
    build_default_resolver,
)
from bot.perception import build_default_perception
from bot.observations import ObservationBatch
from bot.state import ResolutionStatus
from tools.incremental_perception_evaluation import (
    IncrementalEvaluationStats,
    evaluate_detector_frame_pairs,
)
from tools.semantic_slice_evaluation import (
    CONFIRMED,
    MANIFEST_VERSION,
    ManifestEntry,
    load_manifest,
    validate_relative_path,
)

DEFAULT_MANIFEST_PATHS = (
    "datasets/semantic_slice_manifest.json",
    "datasets/semantic_acquisition_manifest.json",
    "datasets/workbench_evidence_manifest.json",
    "datasets/quick_menu_evidence_manifest.json",
    "datasets/black_market_interruptions_manifest.json",
    "datasets/world_boss_semantic_manifest.json",
    "datasets/socket_inventory_full_evidence_manifest.json",
    "datasets/world_boss_bag_full_evidence_manifest.json",
    "datasets/equipment_inventory_full_semantic_manifest.json",
    "datasets/socket_inventory_relief_semantic_manifest.json",
)
DEFAULT_WORKBENCH_MANIFEST = "datasets/workbench_evidence_manifest.json"
DEFAULT_WORKBENCH_ARTIFACTS = "artifacts/workbench"
DEFAULT_CACHE_PATH = "artifacts/semantic_slice/production-pairs-cache.json"
PROMOTABLE_WORKBENCH_STATUS = "raw_unreviewed"
WORKBENCH_SOURCE = "workbench"
SUPPORTED_WORKBENCH_EVENT_SCHEMAS = frozenset({"1.0", "2.0"})


@dataclass(frozen=True)
class DetectorMetrics:
    positives_confirmed: int
    negatives_confirmed: int
    observations_emitted: int
    true_positives: int
    false_positives: int
    false_negatives: int
    raw_negative_anchor: float
    raw_positive_anchor: float
    raw_gap: float
    raw_positive_min: float
    raw_positive_median: float
    raw_positive_max: float
    raw_negative_max: float
    positive_confidence_min: float | None
    positive_confidence_max: float | None
    max_negative_confidence: float


@dataclass(frozen=True)
class ContextMetrics:
    count: int
    correct: int
    unknown: int
    ambiguous: int
    wrong: int


@dataclass(frozen=True)
class ResolverMetrics:
    entries: int
    correct_resolutions: int
    unknown: int
    ambiguous: int
    wrong: int
    overlays_correct: int
    black_market_correct: int
    purchase_overlay_correct: int
    quick_menu_overlay_correct: int
    insufficient_gold_overlay_correct: int
    inventory_full_overlay_correct: int
    black_market_plus_overlay_correct: int
    unknown_plus_purchase_overlay_correct: int
    by_ground_truth: dict[str, ContextMetrics]


@dataclass(frozen=True)
class FrameResult:
    path: str
    ground_truth_base: str
    ground_truth_overlays: tuple[str, ...]
    status: str
    resolved_base: str | None
    resolved_overlays: tuple[str, ...]


@dataclass(frozen=True)
class ProductionPerceptionReport:
    detectors: dict[str, DetectorMetrics]
    resolver: ResolverMetrics
    frames: tuple[FrameResult, ...]
    evaluation: IncrementalEvaluationStats


@dataclass(frozen=True)
class WorkbenchEvidenceMetadata:
    """Non-sensitive provenance for one explicitly selected Workbench frame."""

    source: str
    session_id: str
    sequence: int
    event_timestamp_utc: str
    evidence_reason: str
    frame_shape: tuple[int, int, int]

    def __post_init__(self) -> None:
        if self.source != WORKBENCH_SOURCE:
            raise ValueError("workbench evidence source must be 'workbench'")
        if (
            not isinstance(self.session_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.session_id)
            or self.session_id in {".", ".."}
        ):
            raise ValueError("session_id must be a safe relative identifier")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("sequence must be a positive integer")
        if not isinstance(self.event_timestamp_utc, str) or not self.event_timestamp_utc:
            raise ValueError("event_timestamp_utc must be a non-empty string")
        if not isinstance(self.evidence_reason, str) or not self.evidence_reason:
            raise ValueError("evidence_reason must be a non-empty string")
        shape = tuple(self.frame_shape)
        if (
            len(shape) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in shape
            )
            or shape[2] != 3
        ):
            raise ValueError("frame_shape must be positive (height, width, 3)")
        object.__setattr__(self, "frame_shape", shape)


@dataclass(frozen=True)
class WorkbenchEvidenceRecord:
    entry: ManifestEntry
    metadata: WorkbenchEvidenceMetadata

    def __post_init__(self) -> None:
        if self.entry.review_status != CONFIRMED:
            raise ValueError("workbench evidence must be human-confirmed")


def load_workbench_evidence_manifest(
    path: str | Path,
) -> tuple[WorkbenchEvidenceRecord, ...]:
    """Load the compatible curated manifest while preserving provenance."""

    path = Path(path)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("unsupported Workbench evidence manifest version")
    records = []
    for item in payload.get("entries", ()):
        entry = ManifestEntry(
            path=item["path"],
            base_context=item.get("base_context"),
            overlays=tuple(item.get("overlays", ())),
            review_status=item["review_status"],
        )
        metadata = dict(item["metadata"])
        metadata["frame_shape"] = tuple(metadata["frame_shape"])
        records.append(
            WorkbenchEvidenceRecord(
                entry=entry,
                metadata=WorkbenchEvidenceMetadata(**metadata),
            )
        )
    keys = tuple(
        (record.metadata.session_id, record.metadata.sequence)
        for record in records
    )
    paths = tuple(record.entry.path for record in records)
    if len(keys) != len(set(keys)):
        raise ValueError("Workbench session/sequence selections must be unique")
    if len(paths) != len(set(paths)):
        raise ValueError("Workbench evidence manifest paths must be unique")
    return tuple(records)


def materialize_workbench_evidence(
    repository_root: str | Path,
    *,
    manifest_path: str | Path = DEFAULT_WORKBENCH_MANIFEST,
    artifacts_root: str | Path = DEFAULT_WORKBENCH_ARTIFACTS,
) -> tuple[WorkbenchEvidenceRecord, ...]:
    """Validate selected raw events and copy their untouched PNGs locally.

    Promotion is deliberately manifest-driven. A raw session is eligible only
    when its summary explicitly says ``raw_unreviewed``; diagnostic sessions,
    missing status, predicted labels and path traversal are all rejected.
    """

    repository_root = Path(repository_root).resolve()
    manifest_path = _inside_repository(repository_root, manifest_path)
    artifacts_root = _inside_repository(repository_root, artifacts_root)
    records = load_workbench_evidence_manifest(manifest_path)
    pending_copies: list[tuple[Path, Path]] = []
    production_resolver = build_default_resolver()
    production_bases = {rule.name for rule in production_resolver.base_rules}
    production_overlays = {rule.name for rule in production_resolver.overlay_rules}

    for record in records:
        metadata = record.metadata
        session_root = (artifacts_root / metadata.session_id).resolve()
        _require_descendant(session_root, artifacts_root, "Workbench session")
        summary_path = session_root / "summary.json"
        events_path = session_root / "events.jsonl"
        if not summary_path.is_file() or not events_path.is_file():
            raise FileNotFoundError(
                f"Workbench session metadata is unavailable: {session_root}"
            )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("session_id") != metadata.session_id:
            raise ValueError("Workbench summary session_id does not match its path")
        if summary.get("curation_status") != PROMOTABLE_WORKBENCH_STATUS:
            raise ValueError(
                "Workbench session is not promotable: expected explicit "
                f"{PROMOTABLE_WORKBENCH_STATUS!r} curation_status"
            )
        if summary.get("curated") is True:
            raise ValueError("Workbench session already declares curated=true")

        matching_events = []
        for line_number, line in enumerate(
            events_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid Workbench JSONL at line {line_number}"
                ) from error
            if (
                event.get("event_type") == "evidence.frame"
                and event.get("payload", {}).get("sequence") == metadata.sequence
            ):
                matching_events.append(event)
        if len(matching_events) != 1:
            raise ValueError(
                "selected Workbench sequence must identify exactly one "
                "evidence.frame event"
            )
        event = matching_events[0]
        if event.get("schema_version") not in SUPPORTED_WORKBENCH_EVENT_SCHEMAS:
            raise ValueError("unsupported Workbench evidence event schema_version")
        if event.get("session_id") != metadata.session_id:
            raise ValueError("Workbench event session_id does not match selection")
        payload = event["payload"]
        human = payload.get("human_ground_truth", {})
        if human.get("source") != "human_confirmed":
            raise ValueError("Workbench evidence requires human_confirmed ground truth")
        if human.get("base_is_unknown"):
            event_base = "unknown"
        else:
            event_base = human.get("base_context")
        if (
            event_base != record.entry.base_context
            or tuple(sorted(human.get("overlays", ()))) != record.entry.overlays
        ):
            raise ValueError("curated labels contradict Workbench human ground truth")
        if event_base != "unknown" and event_base not in production_bases:
            raise ValueError(
                "Workbench candidate base is not promotable by the Phase 3F policy"
            )
        if not set(record.entry.overlays).issubset(production_overlays):
            raise ValueError(
                "Workbench candidate overlay is not promotable by the Phase 3F policy"
            )
        if event.get("timestamp") != metadata.event_timestamp_utc:
            raise ValueError("curated timestamp contradicts Workbench event")
        if payload.get("reason") != metadata.evidence_reason:
            raise ValueError("curated evidence reason contradicts Workbench event")
        if tuple(payload.get("frame_shape", ())) != metadata.frame_shape:
            raise ValueError("curated frame shape contradicts Workbench event")

        frame_relative = validate_relative_path(payload.get("frame"))
        frame_parts = PurePosixPath(frame_relative).parts
        if (
            len(frame_parts) != 2
            or frame_parts[0] != "frames"
            or not frame_parts[1].lower().endswith(".png")
        ):
            raise ValueError("Workbench event frame must be directly under frames/")
        source = (session_root / Path(*frame_parts)).resolve()
        _require_descendant(source, session_root / "frames", "Workbench frame")
        source_image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if source_image is None:
            raise FileNotFoundError(f"Workbench frame is unreadable: {source}")
        if tuple(source_image.shape) != metadata.frame_shape:
            raise ValueError("Workbench PNG shape contradicts curated metadata")

        destination = (repository_root / record.entry.path).resolve()
        _require_descendant(destination, repository_root, "curated frame")
        expected_prefix = (
            repository_root
            / "screencaps"
            / "semantic"
            / "workbench"
            / metadata.session_id
        ).resolve()
        _require_descendant(destination, expected_prefix, "curated frame")
        if (
            destination.parent != expected_prefix
            or destination.suffix.lower() != ".png"
        ):
            raise ValueError(
                "curated frame must be a PNG directly under its session directory"
            )
        if destination.exists() and source.read_bytes() != destination.read_bytes():
            raise ValueError(f"curated destination differs from source: {destination}")
        pending_copies.append((source, destination))

    for source, destination in pending_copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
    return records


def _inside_repository(repository_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repository_root / path
    path = path.resolve()
    _require_descendant(path, repository_root, "path")
    return path


def _require_descendant(path: Path, parent: Path, label: str) -> None:
    try:
        path.relative_to(parent.resolve())
    except ValueError as error:
        raise ValueError(f"{label} must remain inside {parent}") from error


def evaluate_production_perception(
    repository_root: str | Path,
    manifest_path: str | Path | Iterable[str | Path] = DEFAULT_MANIFEST_PATHS,
    *,
    cache_path: str | Path | None = DEFAULT_CACHE_PATH,
    full_rebuild: bool = False,
) -> ProductionPerceptionReport:
    """Run production detectors and resolver over every confirmed manifest frame."""

    repository_root = Path(repository_root).resolve()
    manifest_paths = (
        (manifest_path,)
        if isinstance(manifest_path, (str, Path))
        else tuple(manifest_path)
    )
    indexed: dict[str, ManifestEntry] = {}
    for item in manifest_paths:
        path = Path(item)
        if not path.is_absolute():
            path = repository_root / path
        for entry in load_manifest(path):
            if entry.review_status != CONFIRMED:
                continue
            existing = indexed.get(entry.path)
            if existing is not None and existing != entry:
                raise ValueError(f"conflicting human labels for {entry.path}")
            indexed[entry.path] = entry
    entries = tuple(indexed[path] for path in sorted(indexed))
    engine = build_default_perception(repository_root)
    resolver = build_default_resolver()
    production_base_contexts = frozenset(rule.name for rule in resolver.base_rules)
    evaluated_frames, evaluation_stats = evaluate_detector_frame_pairs(
        repository_root,
        (entry.path for entry in entries),
        engine.detectors,
        cache_path=cache_path,
        full_rebuild=full_rebuild,
    )
    evaluated_by_path = {item.path: item for item in evaluated_frames}

    detector_accumulators = {
        spec.name: {
            "positive_confidences": [],
            "negative_confidences": [],
            "positive_raw_scores": [],
            "negative_raw_scores": [],
            "emitted": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "positives": 0,
            "negatives": 0,
        }
        for spec in (
            detector.spec
            for detector in engine.detectors
            if hasattr(detector, "spec")
        )
    }
    resolver_counts = {
        "correct": 0,
        "unknown": 0,
        "ambiguous": 0,
        "wrong": 0,
        "overlays_correct": 0,
        "black_market_correct": 0,
        "purchase_correct": 0,
        "quick_menu_correct": 0,
        "insufficient_gold_correct": 0,
        "inventory_full_correct": 0,
        "base_overlay_correct": 0,
        "unknown_overlay_correct": 0,
    }
    context_accumulators = {
        name: {
            key: 0
            for key in ("count", "correct", "unknown", "ambiguous", "wrong")
        }
        for name in (*sorted(production_base_contexts), "other_or_unknown")
    }
    frame_results: list[FrameResult] = []

    for sequence, entry in enumerate(entries, start=1):
        evaluated = evaluated_by_path[entry.path]
        batch = ObservationBatch(
            sequence=sequence,
            timestamp=float(sequence),
            observations=evaluated.observations,
        )
        state = resolver.resolve(batch)

        for detector in (
            item for item in engine.detectors if hasattr(item, "spec")
        ):
            name = detector.spec.name
            accumulator = detector_accumulators[name]
            evidence = batch.best(name)
            confidence = evidence.confidence if evidence is not None else 0.0
            raw_score = evaluated.raw_scores[name]
            positive = _is_positive(name, entry)
            confidence_key = (
                "positive_confidences" if positive else "negative_confidences"
            )
            accumulator[confidence_key].append(confidence)
            raw_key = "positive_raw_scores" if positive else "negative_raw_scores"
            accumulator[raw_key].append(raw_score)
            accumulator["positives" if positive else "negatives"] += 1
            if evidence is not None:
                accumulator["emitted"] += 1
            if positive and evidence is not None:
                accumulator["tp"] += 1
            elif positive:
                accumulator["fn"] += 1
            elif evidence is not None:
                accumulator["fp"] += 1

        expected_base = (
            entry.base_context
            if entry.base_context
            in production_base_contexts
            else None
        )
        expected_status = (
            ResolutionStatus.RESOLVED
            if expected_base is not None
            else ResolutionStatus.UNKNOWN
        )
        expected_overlays = entry.overlays
        resolution_correct = (
            state.status is expected_status
            and state.base_context == expected_base
            and state.overlays == expected_overlays
        )
        resolver_counts["correct"] += int(resolution_correct)
        resolver_counts["unknown"] += int(
            state.status is ResolutionStatus.UNKNOWN
        )
        resolver_counts["ambiguous"] += int(
            state.status is ResolutionStatus.AMBIGUOUS
        )
        resolver_counts["wrong"] += int(not resolution_correct)
        resolver_counts["overlays_correct"] += int(
            state.overlays == expected_overlays
        )
        if entry.base_context == SCREEN_BLACK_MARKET:
            resolver_counts["black_market_correct"] += int(
                state.base_context == SCREEN_BLACK_MARKET
            )
        if POPUP_PURCHASE_CONFIRMATION in entry.overlays:
            resolver_counts["purchase_correct"] += int(
                POPUP_PURCHASE_CONFIRMATION in state.overlays
            )
        if MENU_QUICK in entry.overlays:
            resolver_counts["quick_menu_correct"] += int(
                MENU_QUICK in state.overlays
            )
        if POPUP_INSUFFICIENT_GOLD in entry.overlays:
            resolver_counts["insufficient_gold_correct"] += int(
                POPUP_INSUFFICIENT_GOLD in state.overlays
            )
        if POPUP_INVENTORY_FULL in entry.overlays:
            resolver_counts["inventory_full_correct"] += int(
                POPUP_INVENTORY_FULL in state.overlays
            )
        if (
            entry.base_context == SCREEN_BLACK_MARKET
            and POPUP_PURCHASE_CONFIRMATION in entry.overlays
        ):
            resolver_counts["base_overlay_correct"] += int(
                state.base_context == SCREEN_BLACK_MARKET
                and state.overlays == (POPUP_PURCHASE_CONFIRMATION,)
            )
        if (
            entry.base_context != SCREEN_BLACK_MARKET
            and POPUP_PURCHASE_CONFIRMATION in entry.overlays
        ):
            resolver_counts["unknown_overlay_correct"] += int(
                state.status is ResolutionStatus.UNKNOWN
                and state.overlays == (POPUP_PURCHASE_CONFIRMATION,)
            )

        context_name = (
            entry.base_context
            if entry.base_context
            in production_base_contexts
            else "other_or_unknown"
        )
        context = context_accumulators[context_name]
        base_correct = (
            state.status is expected_status
            and state.base_context == expected_base
        )
        context["count"] += 1
        context["correct"] += int(base_correct)
        context["unknown"] += int(state.status is ResolutionStatus.UNKNOWN)
        context["ambiguous"] += int(state.status is ResolutionStatus.AMBIGUOUS)
        context["wrong"] += int(
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != expected_base
        )
        frame_results.append(
            FrameResult(
                path=entry.path,
                ground_truth_base=entry.base_context,
                ground_truth_overlays=entry.overlays,
                status=state.status.value,
                resolved_base=state.base_context,
                resolved_overlays=state.overlays,
            )
        )

    detector_metrics = {}
    for name, values in detector_accumulators.items():
        positive_confidences = values["positive_confidences"]
        negative_confidences = values["negative_confidences"]
        positive_raw_scores = values["positive_raw_scores"]
        negative_raw_scores = values["negative_raw_scores"]
        raw_negative_anchor = max(negative_raw_scores)
        raw_positive_anchor = min(positive_raw_scores)
        detector_metrics[name] = DetectorMetrics(
            positives_confirmed=values["positives"],
            negatives_confirmed=values["negatives"],
            observations_emitted=values["emitted"],
            true_positives=values["tp"],
            false_positives=values["fp"],
            false_negatives=values["fn"],
            raw_negative_anchor=raw_negative_anchor,
            raw_positive_anchor=raw_positive_anchor,
            raw_gap=raw_positive_anchor - raw_negative_anchor,
            raw_positive_min=min(positive_raw_scores),
            raw_positive_median=median(positive_raw_scores),
            raw_positive_max=max(positive_raw_scores),
            raw_negative_max=max(negative_raw_scores),
            positive_confidence_min=(
                min(positive_confidences) if positive_confidences else None
            ),
            positive_confidence_max=(
                max(positive_confidences) if positive_confidences else None
            ),
            max_negative_confidence=max(negative_confidences, default=0.0),
        )

    return ProductionPerceptionReport(
        detectors=detector_metrics,
        resolver=ResolverMetrics(
            entries=len(entries),
            correct_resolutions=resolver_counts["correct"],
            unknown=resolver_counts["unknown"],
            ambiguous=resolver_counts["ambiguous"],
            wrong=resolver_counts["wrong"],
            overlays_correct=resolver_counts["overlays_correct"],
            black_market_correct=resolver_counts["black_market_correct"],
            purchase_overlay_correct=resolver_counts["purchase_correct"],
            quick_menu_overlay_correct=resolver_counts["quick_menu_correct"],
            insufficient_gold_overlay_correct=resolver_counts[
                "insufficient_gold_correct"
            ],
            inventory_full_overlay_correct=resolver_counts[
                "inventory_full_correct"
            ],
            black_market_plus_overlay_correct=resolver_counts["base_overlay_correct"],
            unknown_plus_purchase_overlay_correct=resolver_counts[
                "unknown_overlay_correct"
            ],
            by_ground_truth={
                name: ContextMetrics(**values)
                for name, values in context_accumulators.items()
            },
        ),
        frames=tuple(frame_results),
        evaluation=evaluation_stats,
    )


def _is_positive(name: str, entry: ManifestEntry) -> bool:
    if name == LANDMARK_BATTLE_MODE_SELECT_HEADER:
        return entry.base_context == SCREEN_BATTLE_MODE_SELECT
    if name == LANDMARK_LOBBY_TRADING_CENTER_LABEL:
        return entry.base_context == SCREEN_LOBBY
    if name == LANDMARK_CHARACTER_SELECT_HEADER:
        return entry.base_context == SCREEN_CHARACTER_SELECT
    if name == LANDMARK_COMBINE_FUSE_TAB:
        return entry.base_context == SCREEN_COMBINE
    if name == LANDMARK_COMBINE_FUSE_ACTIVE:
        return MODE_COMBINE_FUSE in entry.overlays
    if name == LANDMARK_COMBINE_TRANSMUTE_ACTIVE:
        return MODE_COMBINE_TRANSMUTE in entry.overlays
    if name in {
        INDICATOR_COMBINE_ROWS,
        INDICATOR_COMBINE_ROWS_UPPER,
        INDICATOR_COMBINE_ROW_BOTTOM,
        ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    }:
        return name in entry.observations
    if name == LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE:
        return PANEL_COMBINE_AWAKENED_TRANSMUTE in entry.overlays
    if name == LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE:
        return PANEL_COMBINE_ETHEREAL_RANDOM_PART in entry.overlays
    if name == LANDMARK_COMBINE_ALL_TITLE:
        return POPUP_COMBINE_ALL in entry.overlays
    if name == LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT:
        return POPUP_ETHEREAL_MASS_COMBINE in entry.overlays
    if name == LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT:
        return POPUP_ETHEREAL_NO_MATERIAL in entry.overlays
    if name == LANDMARK_BLACK_MARKET_TITLE:
        return entry.base_context == SCREEN_BLACK_MARKET
    if name == LANDMARK_PURCHASE_CONFIRMATION_PROMPT:
        return POPUP_PURCHASE_CONFIRMATION in entry.overlays
    if name == LANDMARK_INSUFFICIENT_GOLD_PROMPT:
        return POPUP_INSUFFICIENT_GOLD in entry.overlays
    if name == LANDMARK_INVENTORY_FULL_OK_BUTTON:
        return POPUP_INVENTORY_FULL in entry.overlays
    if name == LANDMARK_QUICK_MENU_LOBBY_TILE:
        return MENU_QUICK in entry.overlays
    if name == LANDMARK_SOCKET_TAB:
        return entry.base_context == SCREEN_SOCKET
    if name == LANDMARK_SOCKET_INVENTORY_FULL_PROMPT:
        return POPUP_SOCKET_INVENTORY_FULL in entry.overlays
    if name == LANDMARK_SOCKET_ENHANCE_ALL_TITLE:
        return POPUP_SOCKET_ENHANCE_ALL in entry.overlays
    if name == LANDMARK_SOCKET_NO_MATERIAL_PROMPT:
        return POPUP_SOCKET_NO_MATERIAL in entry.overlays
    if name == LANDMARK_SOCKET_SELL_BULK_BUTTON:
        return POPUP_SOCKET_SELL in entry.overlays
    if name == LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE:
        return LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE in entry.observations
    if name == LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER:
        return OVERLAY_WORLD_BOSS_SELECT_BOSS in entry.overlays
    if name == LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE:
        return POPUP_WORLD_BOSS_PREVIOUS_REWARDS in entry.overlays
    if name == LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT:
        return POPUP_EQUIPMENT_INVENTORY_FULL in entry.overlays
    if name == LANDMARK_WORLD_BOSS_SAPPHIRES_USED:
        return entry.base_context == SCREEN_WORLD_BOSS
    if name == LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE:
        return entry.base_context == SCREEN_WORLD_BOSS_BATTLE
    if name == LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE:
        return OVERLAY_WORLD_BOSS_RAID_COMPLETE in entry.overlays
    raise ValueError(f"Unsupported production detector: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", action="append")
    parser.add_argument(
        "--materialize-workbench",
        action="store_true",
        help="validate the curated Workbench manifest and copy selected raw PNGs",
    )
    parser.add_argument(
        "--workbench-manifest", default=DEFAULT_WORKBENCH_MANIFEST
    )
    parser.add_argument(
        "--workbench-artifacts", default=DEFAULT_WORKBENCH_ARTIFACTS
    )
    parser.add_argument(
        "--output", default="artifacts/semantic_slice/phase3f-production.json"
    )
    parser.add_argument(
        "--cache",
        default=DEFAULT_CACHE_PATH,
        help="regenerable detector/frame result cache",
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="ignore cached pairs and perform a full global audit",
    )
    arguments = parser.parse_args(argv)

    if arguments.materialize_workbench:
        records = materialize_workbench_evidence(
            arguments.repo_root,
            manifest_path=arguments.workbench_manifest,
            artifacts_root=arguments.workbench_artifacts,
        )
        print(f"Materialized {len(records)} curated Workbench frames")
        return 0

    report = evaluate_production_perception(
        arguments.repo_root,
        arguments.manifest
        or DEFAULT_MANIFEST_PATHS,
        cache_path=arguments.cache,
        full_rebuild=arguments.full_rebuild,
    )
    output_path = Path(arguments.output)
    if not output_path.is_absolute():
        output_path = Path(arguments.repo_root).resolve() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    stats = report.evaluation
    print(
        "pairs="
        f"{stats.total_pairs} cache_hits={stats.cache_hits} "
        f"evaluated={stats.evaluated_pairs} "
        f"invalidations={stats.invalidations} "
        f"cache_rebuilt={str(stats.cache_rebuilt).lower()} "
        f"duration={stats.duration_seconds:.3f}s "
        f"wrong={report.resolver.wrong} "
        f"ambiguous={report.resolver.ambiguous} "
        f"result={'PASS' if report.resolver.wrong == 0 else 'FAIL'}"
    )
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
