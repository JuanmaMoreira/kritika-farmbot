"""Offline evidence benchmark. Run from the repository root as a module."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time

import cv2
import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.event_log import RuntimeEventStream
from bot.failure_cause import FailureCause
from bot.failure_evidence import FailureEvidence, MAX_SIDE, WINDOW, publish_failure
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState


def distribution(values):
    ordered = sorted(values)
    return {"median_ms": statistics.median(values) * 1000,
            "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * .95))] * 1000}


def make_snapshot(image, sequence):
    # Representative metadata load, explicitly synthetic semantics (no inference/OCR).
    batch = ObservationBatch(sequence, float(sequence), tuple(
        Observation(f"landmark.synthetic_{i}", .9, ObservationSource.SYSTEM,
                    region=(.1, .2, .3, .4)) for i in range(80)))
    return RuntimeSnapshot(FrameSnapshot(image, float(sequence), sequence), batch,
                           ResolvedState(ResolutionStatus.UNKNOWN, sequence, float(sequence)),
                           RuntimeFacts(), FrameGeometry.from_frame(image))


def benchmark(images, directory, iterations):
    evidence = FailureEvidence(directory)
    stream = RuntimeEventStream(failure_evidence=evidence)
    sequence = 0
    timings = []
    for _ in range(iterations):
        for image in images:
            sequence += 1
            sample = make_snapshot(image, sequence)
            start = time.perf_counter()
            evidence.observe(sample)
            timings.append(time.perf_counter() - start)
    retained = evidence.retained_bytes
    write_times, bundle_bytes = [], []
    for _ in range(iterations):
        start = time.perf_counter()
        linked = publish_failure(stream, "flow.failed", FailureCause("synthetic_failure", "benchmark"))
        write_times.append(time.perf_counter() - start)
        if not linked.evidence_ref:
            raise RuntimeError("benchmark writer did not produce evidence")
    for bundle in directory.iterdir():
        bundle_bytes.append(sum(path.stat().st_size for path in bundle.iterdir()))
    variants = []
    for side in (None, MAX_SIDE):
        frames = []
        for image in images:
            height, width = image.shape[:2]
            ratio = min(1.0, side / max(height, width)) if side else 1.0
            frames.append(cv2.resize(image, (round(width * ratio), round(height * ratio)),
                                     interpolation=cv2.INTER_AREA) if ratio < 1 else image)
        for compression in (1, 3, 6):
            times = []
            for _ in range(min(iterations, 5)):
                size = 0
                start = time.perf_counter()
                for image in frames:
                    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, compression])
                    if not ok:
                        raise RuntimeError("benchmark encoding failed")
                    size += encoded.nbytes
                times.append(time.perf_counter() - start)
            variants.append({"max_side": side, "compression": compression,
                             "png_bytes_three_frames": size, **distribution(times)})
    evidence.close()
    return {
        "frame_shapes": [list(image.shape) for image in images],
        "original_three_frames_bytes": sum(image.nbytes for image in images),
        "ring_array_and_metadata_bytes": retained,
        "ring_ingest_per_fresh_snapshot": distribution(timings),
        "bundle_write": distribution(write_times),
        "bundle_bytes_median": statistics.median(bundle_bytes),
        "encoding_variants": variants,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, nargs=WINDOW, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("iterations must be positive")
    images = [cv2.imread(str(path)) for path in args.frames]
    if any(image is None for image in images):
        parser.error("all three frames must be readable")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    with tempfile.TemporaryDirectory(prefix="evidence-benchmark-", dir=args.output.parent) as temporary:
        root = Path(temporary)
        report = {
            "iterations": args.iterations,
            "inputs": [path.as_posix() for path in args.frames],
            "semantics": "80 synthetic observations per frame; no perception or OCR",
            "local": benchmark(images, root / "local", args.iterations),
            "noise": benchmark([rng.integers(0, 256, image.shape, dtype=np.uint8) for image in images],
                               root / "noise", args.iterations),
        }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {k: v for k, v in report[key].items() if k != "encoding_variants"}
                      for key in ("local", "noise")}, indent=2))


if __name__ == "__main__":
    main()
