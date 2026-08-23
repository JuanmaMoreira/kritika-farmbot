"""Human-directed semantic screenshot acquisition over the 0.2 frame source.

Labels are selected explicitly with the keyboard and are never inferred from
templates, Perception or ContextResolver. Importing this module performs no IO.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Iterable

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.adb import AdbError
from bot.capture import CaptureError, FrameSnapshot
from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
)
from bot.config import RuntimeConfig
from bot.runtime import build_frame_source
from tools.semantic_slice_evaluation import (
    CONFIRMED,
    MANIFEST_VERSION,
    ManifestEntry,
    validate_relative_path,
)

DEFAULT_OUTPUT = Path("screencaps/semantic")
DEFAULT_MANIFEST = Path("datasets/semantic_acquisition_manifest.json")
WINDOW = "Semantic acquisition | 1 Lobby  2 Character  3 Battle  SPACE Save  Q Quit"
NEAR_DUPLICATE_THRESHOLD = 0.01

LABEL_KEYS = {
    ord("1"): SCREEN_LOBBY,
    ord("2"): SCREEN_CHARACTER_SELECT,
    ord("3"): SCREEN_BATTLE_MODE_SELECT,
}
LABEL_DIRECTORIES = {
    SCREEN_LOBBY: "lobby",
    SCREEN_CHARACTER_SELECT: "character_select",
    SCREEN_BATTLE_MODE_SELECT: "battle_mode_select",
}


@dataclass(frozen=True)
class CaptureMetadata:
    """Non-sensitive provenance for one human-confirmed full screenshot."""

    captured_at_utc: str
    width: int
    height: int
    source_sequence: int
    capture_method: str = "human_keyboard"
    previous_label_difference: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.captured_at_utc, str) or not self.captured_at_utc:
            raise ValueError("captured_at_utc must be a non-empty string")
        for name in ("width", "height", "source_sequence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.capture_method != "human_keyboard":
            raise ValueError("capture_method must document explicit human labeling")
        difference = self.previous_label_difference
        if difference is not None and not 0.0 <= float(difference) <= 1.0:
            raise ValueError("previous_label_difference must be in [0, 1]")


@dataclass(frozen=True)
class AcquisitionRecord:
    entry: ManifestEntry
    metadata: CaptureMetadata

    def __post_init__(self) -> None:
        if self.entry.review_status != CONFIRMED:
            raise ValueError("acquisition records must be human-confirmed")
        if self.entry.base_context not in LABEL_DIRECTORIES:
            raise ValueError("acquisition record has an unsupported target label")
        if self.entry.overlays:
            raise ValueError("directed base-screen acquisition does not label overlays")


def mean_frame_difference(first: np.ndarray, second: np.ndarray) -> float:
    """Return a cheap normalized visual difference for duplicate warnings."""

    def thumbnail(frame: np.ndarray) -> np.ndarray:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.size == 0:
            raise ValueError("frames must be non-empty HxWxC NumPy arrays")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)

    left = thumbnail(first).astype(np.float32)
    right = thumbnail(second).astype(np.float32)
    return float(np.mean(np.abs(left - right)) / 255.0)


def capture_path(
    repository_root: str | Path,
    output_directory: str | Path,
    label: str,
    captured_at: dt.datetime,
) -> tuple[Path, str]:
    """Build a lossless output path and its POSIX repository-relative form."""

    if label not in LABEL_DIRECTORIES:
        raise ValueError(f"unsupported acquisition label: {label!r}")
    repository_root = Path(repository_root).resolve()
    output_directory = Path(output_directory)
    if not output_directory.is_absolute():
        output_directory = repository_root / output_directory
    output_directory = output_directory.resolve()
    try:
        output_directory.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("output directory must remain inside the repository") from error

    timestamp = captured_at.astimezone(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%S_%fZ"
    )
    path = output_directory / LABEL_DIRECTORIES[label] / f"{timestamp}.png"
    relative = validate_relative_path(path.relative_to(repository_root).as_posix())
    return path, relative


def load_acquisition_manifest(path: str | Path) -> tuple[AcquisitionRecord, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("unsupported semantic acquisition manifest version")
    records = []
    for item in payload.get("entries", ()):
        entry = ManifestEntry(
            path=item["path"],
            base_context=item.get("base_context"),
            overlays=tuple(item.get("overlays", ())),
            review_status=item["review_status"],
        )
        records.append(
            AcquisitionRecord(entry, CaptureMetadata(**item["metadata"]))
        )
    paths = tuple(record.entry.path for record in records)
    if len(paths) != len(set(paths)):
        raise ValueError("acquisition manifest paths must be unique")
    return tuple(records)


def write_acquisition_manifest(
    path: str | Path, records: Iterable[AcquisitionRecord]
) -> None:
    path = Path(path)
    records = tuple(sorted(records, key=lambda record: record.entry.path))
    paths = tuple(record.entry.path for record in records)
    if len(paths) != len(set(paths)):
        raise ValueError("acquisition manifest paths must be unique")
    payload = {
        "version": MANIFEST_VERSION,
        "entries": [
            {**asdict(record.entry), "metadata": asdict(record.metadata)}
            for record in records
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def record_snapshot(
    repository_root: str | Path,
    output_directory: str | Path,
    snapshot: FrameSnapshot,
    label: str,
    captured_at: dt.datetime,
    previous_label_frame: np.ndarray | None,
) -> AcquisitionRecord:
    """Persist one untouched full PNG selected and confirmed by the user."""

    path, relative = capture_path(
        repository_root, output_directory, label, captured_at
    )
    difference = (
        None
        if previous_label_frame is None
        else mean_frame_difference(previous_label_frame, snapshot.image)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), snapshot.image):
        raise OSError(f"OpenCV could not save screenshot: {path}")
    return AcquisitionRecord(
        ManifestEntry(relative, label, (), CONFIRMED),
        CaptureMetadata(
            captured_at_utc=captured_at.astimezone(dt.timezone.utc).isoformat(),
            width=snapshot.width,
            height=snapshot.height,
            source_sequence=snapshot.sequence,
            previous_label_difference=difference,
        ),
    )


def _display_frame(
    frame: np.ndarray,
    label: str | None,
    counts: dict[str, int],
) -> np.ndarray:
    display = frame.copy()
    lines = [
        f"label: {label or '<select with 1/2/3>'}",
        " | ".join(
            f"{LABEL_DIRECTORIES[name]}={counts[name]}"
            for name in LABEL_DIRECTORIES
        ),
        "SPACE saves with the selected human label; Q exits",
    ]
    for index, text in enumerate(lines):
        y = 40 + index * 38
        cv2.putText(
            display, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
            (0, 0, 0), 5, cv2.LINE_AA,
        )
        cv2.putText(
            display, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
            (255, 255, 255), 2, cv2.LINE_AA,
        )
    return display


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "--adb-executable",
        type=Path,
        help="optional explicit ADB executable override for this session",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    repository_root = arguments.repo_root.resolve()
    manifest_path = arguments.manifest
    if not manifest_path.is_absolute():
        manifest_path = repository_root / manifest_path

    try:
        records = list(load_acquisition_manifest(manifest_path))
        counts = {
            label: sum(record.entry.base_context == label for record in records)
            for label in LABEL_DIRECTORIES
        }
        config = RuntimeConfig.from_env(dotenv_path=arguments.dotenv)
        if arguments.adb_executable is not None:
            config = replace(
                config, adb_executable=str(arguments.adb_executable.resolve())
            )
        source = build_frame_source(config)
        state = source.adb.get_state()
        if state != "device":
            raise CaptureError(f"ADB state must be 'device', got {state!r}")

        print("ADB state=device. Connecting through ScrcpyFrameSource...")
        print("1 Lobby | 2 Character Select | 3 Battle Mode Select")
        print("SPACE save confirmed full frame | Q quit")
        selected_label: str | None = None
        previous_frames: dict[str, np.ndarray] = {}
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

        with source:
            while True:
                snapshot = source.get_frame()
                cv2.imshow(
                    WINDOW,
                    _display_frame(snapshot.image, selected_label, counts),
                )
                key = cv2.waitKey(50) & 0xFF
                if key in (ord("q"), ord("Q")):
                    break
                if key in LABEL_KEYS:
                    selected_label = LABEL_KEYS[key]
                    print(f"Selected human label: {selected_label}")
                    continue
                if key == ord(" "):
                    if selected_label is None:
                        print("[WARN] Select label 1, 2 or 3 before saving.")
                        continue
                    now = dt.datetime.now(dt.timezone.utc)
                    record = record_snapshot(
                        repository_root,
                        arguments.output,
                        snapshot,
                        selected_label,
                        now,
                        previous_frames.get(selected_label),
                    )
                    records.append(record)
                    write_acquisition_manifest(manifest_path, records)
                    counts[selected_label] += 1
                    previous_frames[selected_label] = snapshot.image.copy()
                    difference = record.metadata.previous_label_difference
                    duplicate_note = (
                        " [NEAR-DUPLICATE WARNING]"
                        if difference is not None
                        and difference < NEAR_DUPLICATE_THRESHOLD
                        else ""
                    )
                    print(
                        f"Saved {record.entry.path} label={selected_label} "
                        f"difference={difference!r}{duplicate_note}"
                    )
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
    except KeyboardInterrupt:
        print("Acquisition interrupted; capture resources released.", file=sys.stderr)
        return 130
    except (AdbError, CaptureError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
