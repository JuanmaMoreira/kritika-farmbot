"""Offline identity audit; never connects to a device or executes input."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from bot.catalog import SCREEN_CHARACTER_SELECT, SCREEN_LOBBY, build_default_resolver
from bot.character_identity import (
    LOBBY_PERSONAL_NAME_ROI, MIN_NAME_CONFIDENCE, PERSONAL_NAME_CLASSES,
    KNOWN_LOBBY_NAME_OCR_VARIANTS, LobbyNameRecognizer,
)
from bot.geometry import relative_region_to_pixels
from bot.observations import ObservationBatch
from bot.ocr import RapidOcrEngine
from bot.perception import build_default_perception
from bot.state import ResolutionStatus
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs
from tools.production_perception_evaluation import DEFAULT_CACHE_PATH, DEFAULT_MANIFEST_PATHS
from tools.semantic_slice_evaluation import ManifestEntry, load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/character_identity_manifest.json"

# Acquisition labels explicitly associated with the user's ground truth.
# These aliases are never imported by the runtime recognizer.
ACQUISITION_NAMES = {
    "draken3bb": "DRAKEN三BB", "draken1bk": "DRAKEN一BK", "draken2db": "DRAKEN二DB",
    "drakenn25": "Drakenn25", "drakenn13": "Drakenn13", "drakenn10": "Drakenn10",
    "drakenn09": "Drakenn09", "draken4r": "DRAKEN四R", "drakenn26": "Drakenn26",
    "drakenn20": "Drakenn20", "drakenn19": "Drakenn19", "drakenn23": "Drakenn23",
    "drakenn08": "Drakenn08", "drakenn14": "Drakenn14", "drakenn15": "Drakennn15",
    "drakenn16": "Drakenn16", "drakenn06": "Drakenn06", "drakenn21": "Drakenn21",
    "drakennn17": "Drakennn17", "drakenn24": "Drakenn24", "draken6fs": "DRAKEN六FS",
    "drakenn27": "Drakenn27", "drakenn11": "Drakenn11", "drakenn12": "Drakenn12",
    "drakenn18": "Drakenn18", "draken5m": "DRAKEN五M", "draken4bd": "DRAKEN四BD",
    "drakenn22": "Drakenn22",
}
CURATED = {"drakenn25", "drakenn15", "drakennn17", "draken1bk", "draken2db",
           "draken3bb", "draken4r", "draken4bd", "drakenn22"}
EXTRA_NEGATIVE_MANIFESTS = (
    "datasets/portal_notification_evidence_manifest.json",
    "datasets/world_boss_quick_menu_evidence_manifest.json",
)


def read_image(path):
    frame = cv2.imread(str(ROOT / path))
    if frame is None:
        raise ValueError(f"missing/unreadable evidence: {path}")
    return frame


def curate():
    """Preserve all provenance; promote only 18 small regression crops."""
    entries = []
    for slug, name in ACQUISITION_NAMES.items():
        paths = sorted((ROOT / "artifacts/identity_name").glob(f"*_{slug}_seq*.png"),
                       key=lambda p: int(p.stem.rsplit("seq", 1)[1]))
        if len(paths) != 3:
            raise ValueError(f"expected three raw frames for {slug}")
        for index, path in enumerate(paths):
            relative = path.relative_to(ROOT).as_posix()
            entry = dict(path=relative, personal_name=name, class_name=PERSONAL_NAME_CLASSES[name],
                         split="calibration" if index == 0 else "validation",
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if slug in CURATED and index > 0:
                frame = read_image(relative)
                h, w = frame.shape[:2]
                x1, y1, x2, y2 = relative_region_to_pixels(LOBBY_PERSONAL_NAME_ROI, w, h)
                crop_path = ROOT / f"tests/fixtures/identity_name/{slug}_{index}.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(crop_path), frame[y1:y2, x1:x2]):
                    raise OSError(f"cannot write {crop_path}")
                entry["crop"] = crop_path.relative_to(ROOT).as_posix()
                entry["crop_sha256"] = hashlib.sha256(crop_path.read_bytes()).hexdigest()
            entries.append(entry)
    payload = dict(version=1, curation={
        "ground_truth": "Authoritative user handoff 2026-09-07; exact personal_name -> class_name",
        "roi": LOBBY_PERSONAL_NAME_ROI,
        "frame_size": [2712, 1224],
        "split": "First sequence per character for calibration; other two for validation. Same acquisition, not independent sessions.",
        "chat": "ROI disjoint from observed chat [0.44, 0.12, 0.85, 0.21]; see socket_inventory_relief_semantic_manifest.json",
        "raw_retention": "All 84 originals retained pending user review; never purged by this tool",
        "runtime_assets": "None; crops are test fixtures, never runtime templates",
    }, entries=entries)
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class RecordingEngine:
    def __init__(self):
        self.engine = RapidOcrEngine()
        self.last = None

    def recognize(self, image):
        self.last = self.engine.recognize(image)
        return self.last


def evaluate(*, corpus=False):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    engine = RecordingEngine()
    recognizer = LobbyNameRecognizer(engine)
    perception = build_default_perception(ROOT)
    resolver = build_default_resolver()
    raw_entries = {e["path"]: e for e in manifest["entries"]}
    for path, entry in raw_entries.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"raw evidence changed: {path}")
    existing = {}
    extra = {}
    if corpus:
        for path in DEFAULT_MANIFEST_PATHS:
            for entry in load_manifest(ROOT / path):
                if entry.review_status == "confirmed":
                    existing[entry.path] = entry
        for path in EXTRA_NEGATIVE_MANIFESTS:
            for entry in load_manifest(ROOT / path):
                if entry.review_status == "confirmed" and entry.path not in existing:
                    extra[entry.path] = entry
        # Both plus-positive and plus-negative sentinel samples are Character
        # Select screens: negative contexts for Lobby identity, not name labels.
        sentinel = json.loads((ROOT / "datasets/character_select_sentinel_manifest.json").read_text(encoding="utf-8"))
        for entry in sentinel["positives"] + sentinel["negatives"]:
            if entry["path"] not in existing:
                extra[entry["path"]] = ManifestEntry(entry["path"], SCREEN_CHARACTER_SELECT, (), "confirmed")
    historical = existing | extra
    frames, stats = evaluate_detector_frame_pairs(
        ROOT, sorted(raw_entries.keys() | historical.keys()), perception.detectors,
        cache_path=DEFAULT_CACHE_PATH,
    )
    rows = []
    for index, evaluated in enumerate(frames, 1):
        state = resolver.resolve(ObservationBatch(index, float(index), evaluated.observations))
        engine.last = None
        snapshot = SimpleNamespace(state=state, frame=SimpleNamespace(image=read_image(evaluated.path)))
        identity = recognizer.recognize(snapshot)
        raw = raw_entries.get(evaluated.path)
        expected_clean_lobby = (True if raw else
                                historical[evaluated.path].base_context == SCREEN_LOBBY
                                and not historical[evaluated.path].overlays)
        product_clean_lobby = (state.status is ResolutionStatus.RESOLVED
                               and state.base_context == SCREEN_LOBBY and not state.overlays)
        row = dict(path=evaluated.path, split=raw["split"] if raw else "extra_negative" if evaluated.path in extra else "existing",
                   expected_name=raw["personal_name"] if raw else None,
                   recognized_name=identity.personal_name if identity else None,
                   ocr_text=engine.last.text if engine.last else None,
                   ocr_confidence=engine.last.confidence if engine.last else None,
                   expected_clean_lobby=expected_clean_lobby,
                   product_clean_lobby=product_clean_lobby)
        row["recognition_method"] = ("closed_variant" if identity and engine.last.text != identity.personal_name
                                     else "exact" if identity else None)
        if raw:
            row["outcome"] = ("correct" if identity and identity.personal_name == raw["personal_name"]
                              else "wrong" if identity else "fallback")
        else:
            # Old corpus labels screens, not personal names. Do not invent
            # name ground truth for its clean Lobby frames.
            row["outcome"] = ("unlabelled_lobby" if expected_clean_lobby else
                              "false_accept" if identity else "rejected_context")
        rows.append(row)
    fixture_rows = []
    width, height = manifest["curation"]["frame_size"]
    x1, y1, x2, y2 = relative_region_to_pixels(LOBBY_PERSONAL_NAME_ROI, width, height)
    for entry in manifest["entries"]:
        if "crop" not in entry:
            continue
        if hashlib.sha256((ROOT / entry["crop"]).read_bytes()).hexdigest() != entry["crop_sha256"]:
            raise ValueError(f"fixture changed: {entry['crop']}")
        image = np.zeros((height, width, 3), np.uint8)
        image[y1:y2, x1:x2] = read_image(entry["crop"])
        snapshot = SimpleNamespace(frame=SimpleNamespace(image=image), state=SimpleNamespace(
            status=ResolutionStatus.RESOLVED, base_context=SCREEN_LOBBY, overlays=()))
        identity = recognizer.recognize(snapshot)
        fixture_rows.append(dict(path=entry["crop"], expected_name=entry["personal_name"],
                                 recognized_name=identity.personal_name if identity else None,
                                 correct=identity is not None and identity.personal_name == entry["personal_name"]))
    summary = {split: dict(Counter(r["outcome"] for r in rows if r["split"] == split))
               for split in ("calibration", "validation", "existing", "extra_negative")}
    raw_rows = [r for r in rows if r["expected_name"] is not None]
    summary["raw_lobby_mismatches"] = sum(not r["product_clean_lobby"] for r in raw_rows)
    summary["raw_recognition_methods"] = dict(Counter(r["recognition_method"] for r in raw_rows))
    summary["fixtures"] = dict(total=len(fixture_rows), correct=sum(r["correct"] for r in fixture_rows))
    summary["raws_by_name"] = {name: dict(Counter(r["outcome"] for r in raw_rows if r["expected_name"] == name))
                               for name in PERSONAL_NAME_CLASSES}
    summary["min_accepted_ocr_confidence"] = min(
        r["ocr_confidence"] for r in rows if r["outcome"] == "correct")
    output = ROOT / "artifacts/identity_name_evaluation.json"
    output.write_text(json.dumps(dict(threshold=MIN_NAME_CONFIDENCE, summary=summary,
                                     known_ocr_variants=dict(KNOWN_LOBBY_NAME_OCR_VARIANTS),
                                     evaluation=asdict(stats), rows=rows, fixtures=fixture_rows),
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    print(f"pairs={stats.total_pairs} hits={stats.cache_hits} evaluated={stats.evaluated_pairs}")
    return int(any(r["outcome"] in {"wrong", "false_accept"} for r in rows)
               or summary["raw_lobby_mismatches"] > 0 or not all(r["correct"] for r in fixture_rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curate", action="store_true")
    parser.add_argument("--corpus", action="store_true")
    arguments = parser.parse_args()
    if arguments.curate:
        curate()
    return evaluate(corpus=arguments.corpus)


if __name__ == "__main__":
    raise SystemExit(main())
