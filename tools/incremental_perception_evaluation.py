"""Content-addressed detector/frame evaluation for the offline corpus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import inspect
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Iterable

import cv2
import numpy as np

import bot.geometry as geometry_module
import bot.observations as observations_module
import bot.screen as screen_module
import bot.perception.specs as specs_module
from bot.observations import Observation, ObservationSource
from bot.perception.local_cv import LocalCvDetector


CACHE_VERSION = 1
EVALUATOR_LOGIC_VERSION = "production-pairs-v1"


@dataclass(frozen=True)
class EvaluatedFrame:
    path: str
    observations: tuple[Observation, ...]
    raw_scores: dict[str, float]


@dataclass(frozen=True)
class IncrementalEvaluationStats:
    total_pairs: int
    cache_hits: int
    evaluated_pairs: int
    invalidations: int
    cache_rebuilt: bool
    duration_seconds: float


def evaluate_detector_frame_pairs(
    repository_root: str | Path,
    frame_paths: Iterable[str | Path],
    detectors: Iterable[object],
    *,
    cache_path: str | Path | None,
    full_rebuild: bool = False,
) -> tuple[tuple[EvaluatedFrame, ...], IncrementalEvaluationStats]:
    """Evaluate required pairs once and safely reuse prior detector outputs.

    The cache contains derived observations only. Human labels and resolver
    outcomes remain outside it and must be recomputed by the caller.
    """

    started = perf_counter()
    root = Path(repository_root).resolve()
    relative_paths = tuple(_relative_frame_path(root, item) for item in frame_paths)
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("frame_paths must be unique")

    detector_items = tuple(detectors)
    detector_ids = tuple(_detector_id(item) for item in detector_items)
    if len(detector_ids) != len(set(detector_ids)):
        raise ValueError("detectors must have unique evaluation identities")
    detector_fingerprints = {
        detector_id: _detector_fingerprint(root, detector)
        for detector_id, detector in zip(detector_ids, detector_items)
    }

    cache_file = _cache_file(root, cache_path)
    cached_pairs, cache_rebuilt = _load_cache(cache_file)
    if full_rebuild:
        cached_pairs = {}
        cache_rebuilt = True

    next_pairs: dict[str, dict[str, object]] = {}
    evaluated_frames: list[EvaluatedFrame] = []
    cache_hits = 0
    evaluated_pairs = 0
    invalidations = 0

    for relative_path in relative_paths:
        absolute_path = (root / Path(relative_path)).resolve()
        frame_bytes = absolute_path.read_bytes()
        frame_hash = _sha256(frame_bytes)
        pair_results: list[tuple[tuple[Observation, ...], float | None]] = []
        missing: list[tuple[int, object, str, str, str]] = []

        for index, (detector, detector_id) in enumerate(
            zip(detector_items, detector_ids)
        ):
            fingerprint = detector_fingerprints[detector_id]
            logical_key = _logical_pair_key(detector_id, relative_path)
            cached = cached_pairs.get(logical_key)
            restored = _restore_pair(
                cached,
                detector_id=detector_id,
                frame_path=relative_path,
                frame_hash=frame_hash,
                detector_fingerprint=fingerprint,
                raw_score_required=isinstance(detector, LocalCvDetector),
            )
            if restored is None:
                if cached is not None:
                    invalidations += 1
                pair_results.append(((), None))
                missing.append(
                    (index, detector, detector_id, fingerprint, logical_key)
                )
                continue
            cache_hits += 1
            pair_results.append(restored)
            next_pairs[logical_key] = cached

        if missing:
            frame = cv2.imdecode(
                np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if frame is None:
                raise FileNotFoundError(
                    f"Confirmed screenshot is unreadable: {absolute_path}"
                )
            for index, detector, detector_id, fingerprint, logical_key in missing:
                observations, raw_score = _evaluate_pair(detector, frame)
                pair_results[index] = (observations, raw_score)
                next_pairs[logical_key] = _cache_pair(
                    detector_id=detector_id,
                    frame_path=relative_path,
                    frame_hash=frame_hash,
                    detector_fingerprint=fingerprint,
                    observations=observations,
                    raw_score=raw_score,
                )
                evaluated_pairs += 1

        observations = tuple(
            observation
            for pair_observations, _ in pair_results
            for observation in pair_observations
        )
        raw_scores = {
            detector_id: raw_score
            for detector_id, (_, raw_score) in zip(detector_ids, pair_results)
            if raw_score is not None
        }
        evaluated_frames.append(
            EvaluatedFrame(relative_path, observations, raw_scores)
        )

    if cache_file is not None:
        _write_cache(cache_file, next_pairs)

    stats = IncrementalEvaluationStats(
        total_pairs=len(relative_paths) * len(detector_items),
        cache_hits=cache_hits,
        evaluated_pairs=evaluated_pairs,
        invalidations=invalidations,
        cache_rebuilt=cache_rebuilt,
        duration_seconds=perf_counter() - started,
    )
    return tuple(evaluated_frames), stats


def _evaluate_pair(
    detector: object, frame: np.ndarray
) -> tuple[tuple[Observation, ...], float | None]:
    if isinstance(detector, LocalCvDetector):
        detection = detector.measure(frame)
        observations = (
            ()
            if detection.semantic_confidence == 0.0
            else (
                Observation(
                    name=detection.observation_name,
                    confidence=detection.semantic_confidence,
                    source=ObservationSource.LOCAL_CV,
                ),
            )
        )
        return observations, detection.raw_match_score

    detect = getattr(detector, "detect", None)
    if not callable(detect):
        raise ValueError("detectors must provide detect(frame)")
    observations = tuple(detect(frame))
    if not all(isinstance(item, Observation) for item in observations):
        raise ValueError("detectors must emit only Observation instances")
    return observations, None


def _detector_id(detector: object) -> str:
    explicit = getattr(detector, "evaluation_id", None)
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        return explicit
    if isinstance(detector, LocalCvDetector):
        return detector.spec.name
    cls = detector.__class__
    return f"{cls.__module__}.{cls.__qualname__}"


def _detector_fingerprint(repository_root: Path, detector: object) -> str:
    cls = detector.__class__
    public_state = {
        name: value
        for name, value in vars(detector).items()
        if not name.startswith("_") and name not in {"asset_path", "asset_paths"}
    }
    asset_paths = []
    for name in ("asset_path", "asset_paths"):
        value = getattr(detector, name, ())
        candidates = (value,) if isinstance(value, Path) else tuple(value or ())
        asset_paths.extend(Path(item).resolve() for item in candidates)
    unique_assets = tuple(dict.fromkeys(asset_paths))
    payload = {
        "evaluator_logic": EVALUATOR_LOGIC_VERSION,
        "evaluator_source": _source_hash(_evaluate_pair),
        "class": f"{cls.__module__}.{cls.__qualname__}",
        "class_source": _source_hash(cls),
        "shared_sources": {
            module.__name__: _source_hash(module)
            for module in (
                screen_module,
                geometry_module,
                observations_module,
                specs_module,
            )
        },
        "runtime": {"opencv": cv2.__version__, "numpy": np.__version__},
        "config": _canonical(public_state, repository_root),
        "assets": [
            {
                "path": _canonical(path, repository_root),
                "sha256": _sha256(path.read_bytes()),
            }
            for path in unique_assets
        ],
    }
    return _sha256(_canonical_json(payload).encode("utf-8"))


def _source_hash(value: object) -> str:
    source_file = inspect.getsourcefile(value)
    if source_file is None:
        return _sha256(repr(value).encode("utf-8"))
    return _sha256(Path(source_file).read_bytes())


def _canonical(value: object, repository_root: Path) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value), repository_root)
    if isinstance(value, dict):
        return {
            str(key): _canonical(item, repository_root)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item, repository_root) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_canonical(item, repository_root) for item in value),
            key=lambda item: _canonical_json(item),
        )
    if isinstance(value, Path):
        resolved = value.resolve()
        try:
            return resolved.relative_to(repository_root).as_posix()
        except ValueError:
            return resolved.as_posix()
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError(
        f"detector configuration is not safely fingerprintable: {type(value).__name__}"
    )


def _cache_pair(
    *,
    detector_id: str,
    frame_path: str,
    frame_hash: str,
    detector_fingerprint: str,
    observations: tuple[Observation, ...],
    raw_score: float | None,
) -> dict[str, object]:
    return {
        "detector_id": detector_id,
        "frame_path": frame_path,
        "frame_sha256": frame_hash,
        "detector_sha256": detector_fingerprint,
        "observations": [_serialize_observation(item) for item in observations],
        "raw_match_score": raw_score,
    }


def _restore_pair(
    value: object,
    *,
    detector_id: str,
    frame_path: str,
    frame_hash: str,
    detector_fingerprint: str,
    raw_score_required: bool,
) -> tuple[tuple[Observation, ...], float | None] | None:
    if not isinstance(value, dict):
        return None
    if (
        value.get("detector_id") != detector_id
        or value.get("frame_path") != frame_path
        or value.get("frame_sha256") != frame_hash
        or value.get("detector_sha256") != detector_fingerprint
    ):
        return None
    try:
        observations = tuple(
            _deserialize_observation(item) for item in value["observations"]
        )
        raw_score = value.get("raw_match_score")
        if raw_score is not None:
            raw_score = float(raw_score)
            if not math.isfinite(raw_score):
                return None
        if raw_score_required and raw_score is None:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return observations, raw_score


def _serialize_observation(observation: Observation) -> dict[str, object]:
    return {
        "name": observation.name,
        "confidence": observation.confidence,
        "source": observation.source.value,
        "value": observation.value,
        "region": list(observation.region) if observation.region is not None else None,
    }


def _deserialize_observation(value: object) -> Observation:
    if not isinstance(value, dict):
        raise ValueError("cached observation must be an object")
    region = value.get("region")
    return Observation(
        name=value["name"],
        confidence=value["confidence"],
        source=ObservationSource(value["source"]),
        value=value.get("value"),
        region=None if region is None else tuple(region),
    )


def _load_cache(
    cache_file: Path | None,
) -> tuple[dict[str, dict[str, object]], bool]:
    if cache_file is None or not cache_file.exists():
        return {}, False
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload.get("version") != CACHE_VERSION:
            return {}, True
        pairs = payload.get("pairs")
        if not isinstance(pairs, dict) or not all(
            isinstance(key, str) and isinstance(value, dict)
            for key, value in pairs.items()
        ):
            return {}, True
        return pairs, False
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}, True


def _write_cache(cache_file: Path, pairs: dict[str, dict[str, object]]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": CACHE_VERSION, "pairs": pairs}
    temporary = cache_file.with_name(cache_file.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(cache_file)


def _relative_frame_path(repository_root: Path, value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = repository_root / path
    resolved = path.resolve()
    try:
        return resolved.relative_to(repository_root).as_posix()
    except ValueError as error:
        raise ValueError("frame paths must remain inside repository_root") from error


def _cache_file(repository_root: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = repository_root / path
    return path.resolve()


def _logical_pair_key(detector_id: str, frame_path: str) -> str:
    return _sha256(
        _canonical_json([detector_id, frame_path]).encode("utf-8")
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
