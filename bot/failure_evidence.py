"""Local, bounded diagnostic attachments to the canonical runtime event stream."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import re
import threading
import time
from typing import Callable
from uuid import uuid4

import cv2
import numpy as np

from bot.event_context import event_context
from bot.event_log import EventSink, RuntimeEvent
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeSnapshot


WINDOW = 3
MAX_SIDE = 960
PNG_COMPRESSION = 1
MAX_METADATA_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 10 * 1024 * 1024
MAX_STORAGE_BYTES = 128 * 1024 * 1024
MAX_BUNDLES = 20
MAX_AGE_SECONDS = 7 * 86400
_DIRECTORY = re.compile(r"failure_[0-9a-f]{32}")
_FILE = re.compile(r"(?:failure\.json|snapshot_\d+\.json|frame_\d+\.png|\.owner)")
_OWNER = b"kritika-failure-evidence-v1\n"
_TERMINALS = {"flow.failed", "rotation.failed", "session.failed", "runtime.failed"}
_CANCELLATIONS = {"RuntimeWaitCancelled", "KeyboardInterrupt", "SystemExit", "CancelledError"}


def json_bytes(payload: dict) -> bytes:
    """Strict reproducible JSON, never repr/default=str of runtime objects."""
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("evidence metadata exceeds limit")
    return encoded


def snapshot_payload(snapshot: RuntimeSnapshot) -> dict:
    return {
        "schema_version": 1,
        "sequence": snapshot.sequence,
        "timestamp": snapshot.timestamp,
        "timestamp_clock": "capture_monotonic",
        "context": event_context(),
        "observations": [asdict(item) for item in snapshot.observations.observations],
        "state": asdict(snapshot.state),
        "facts": {"gold_slots": sorted(snapshot.facts.gold_slots),
                  "purchased_slots": sorted(snapshot.facts.purchased_slots)},
        "geometry": asdict(snapshot.geometry),
    }


@dataclass(frozen=True)
class _Entry:
    sequence: int
    metadata: bytes
    image: np.ndarray | None


class FailureEvidence:
    """Composition-owned ring/writer; no capture, input, OCR, timers or retries."""

    def __init__(self, root: Path, *, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self._clock = clock
        self._entries: deque[_Entry] = deque(maxlen=WINDOW)
        self._lock = threading.Lock()
        self._closed = False
        try:
            self.root = self.root.resolve()
        except Exception:
            self._closed = True
        try:
            if not self._closed:
                self._prune()
        except Exception:
            pass

    def observe(self, snapshot: RuntimeSnapshot) -> None:
        try:
            with self._lock:
                if self._closed or (self._entries and snapshot.sequence <= self._entries[-1].sequence):
                    return
                payload = snapshot_payload(snapshot)
                image = snapshot.frame.image
                if image is not None:
                    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
                        raise ValueError("evidence expects BGR uint8")
                    height, width = image.shape[:2]
                    ratio = min(1.0, MAX_SIDE / max(height, width))
                    if ratio < 1:
                        image = cv2.resize(image, (max(1, round(width * ratio)), max(1, round(height * ratio))),
                                           interpolation=cv2.INTER_AREA)
                    else:
                        image = image.copy()
                    image.flags.writeable = False
                    payload["frame"] = {"file": f"frame_{snapshot.sequence}.png",
                                        "width": image.shape[1], "height": image.shape[0],
                                        "color_space": "BGR", "png_compression": PNG_COMPRESSION}
                else:
                    payload["frame"] = None
                self._entries.append(_Entry(snapshot.sequence, json_bytes(payload), image))
        except Exception:
            # A bad diagnostic sample cannot prevent delivery of the runtime snapshot.
            pass

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return sum(len(e.metadata) + (e.image.nbytes if e.image is not None else 0)
                       for e in self._entries)

    def close(self) -> None:
        with self._lock:
            self._entries.clear()
            self._closed = True

    def enrich(self, item: RuntimeEvent) -> RuntimeEvent:
        """The only evidence eligibility seam, before any stream consumer runs."""
        cause = item.fields.get("failure")
        if (item.event not in _TERMINALS or not isinstance(cause, dict)
                or cause.get("evidence_ref")
                or cause.get("type") in {"cancelled", "cancellation"}
                or cause.get("exception_type") in _CANCELLATIONS):
            return item
        try:
            with self._lock:
                if self._closed:
                    return item
                return self._write(item, cause)
        except Exception:
            # No diagnostic event here: writing a failure must never recurse.
            return item

    def _write(self, item: RuntimeEvent, cause: dict) -> RuntimeEvent:
        directory = self.root / f"failure_{uuid4().hex}"
        reference = (directory / "failure.json").as_uri()
        enriched = replace(item, fields={**item.fields, "failure": {**cause, "evidence_ref": reference}})
        files: dict[str, bytes] = {}
        snapshots = []
        for entry in self._entries:
            name = f"snapshot_{entry.sequence}.json"
            files[name] = entry.metadata
            frame_name = None
            if entry.image is not None:
                ok, encoded = cv2.imencode(".png", entry.image, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION])
                if not ok:
                    raise OSError("PNG encode failed")
                frame_name = f"frame_{entry.sequence}.png"
                files[frame_name] = encoded.tobytes()
            snapshots.append({"sequence": entry.sequence, "snapshot": name, "frame": frame_name})
        # Only the canonical failure and correlation envelope, not arbitrary event fields.
        payload = enriched.payload()
        files["failure.json"] = json_bytes({
            "evidence_schema_version": 1,
            "failure": enriched.fields["failure"],
            "event": {key: payload.get(key) for key in (
                "schema_version", "run_id", "session_id", "character_index", "flow",
                "operation_id", "parent_operation_id", "step", "event_sequence",
                "timestamp", "event", "component")},
            "snapshots": snapshots,
        })
        size = sum(map(len, files.values())) + len(_OWNER)
        if size > MAX_BUNDLE_BYTES:
            raise ValueError("evidence bundle exceeds limit")
        self._prune(reserve_bytes=size, reserve_count=1)
        directory.mkdir(parents=True, exist_ok=False)
        created = []
        try:
            for name, data in {".owner": _OWNER, **files}.items():
                path = directory / name
                created.append(path)
                with path.open("xb") as output:
                    output.write(data)
            # failure.json is written last. Only now may a consumer see its reference.
            return enriched
        except Exception:
            for path in reversed(created):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                directory.rmdir()
            except OSError:
                pass
            raise

    def _owned_files(self, directory: Path) -> list[Path] | None:
        # Never recursively delete, follow links/junctions, or touch curated additions.
        if (not _DIRECTORY.fullmatch(directory.name) or not directory.is_dir()
                or directory.is_symlink() or directory.resolve() != self.root / directory.name):
            return None
        files = list(directory.iterdir())
        if any(not _FILE.fullmatch(p.name) or not p.is_file() or p.is_symlink()
               or p.resolve() != directory / p.name for p in files):
            return None
        marker = directory / ".owner"
        if marker not in files or marker.read_bytes() != _OWNER:
            return None
        return files

    def _prune(self, *, reserve_bytes: int = 0, reserve_count: int = 0) -> None:
        if reserve_bytes > MAX_STORAGE_BYTES or reserve_count > MAX_BUNDLES:
            raise ValueError("evidence exceeds storage quota")
        if not self.root.exists():
            return
        bundles = []
        for directory in self.root.iterdir():
            files = self._owned_files(directory)
            if files is not None:
                bundles.append((directory.stat().st_mtime, directory, files,
                                sum(p.stat().st_size for p in files)))
        bundles.sort(key=lambda item: (item[0], item[1].name))
        total = sum(item[3] for item in bundles)
        remaining = len(bundles)
        now = self._clock()
        for modified, directory, files, size in bundles:
            if (now - modified <= MAX_AGE_SECONDS and remaining + reserve_count <= MAX_BUNDLES
                    and total + reserve_bytes <= MAX_STORAGE_BYTES):
                break
            for path in files:
                path.unlink()
            directory.rmdir()
            total -= size
            remaining -= 1


def publish_failure(sink: EventSink, event: str, failure: FailureCause | None, **fields) -> FailureCause | None:
    """Publish once and return the same cause with the successfully persisted ref."""
    if failure is None and event in _TERMINALS:
        failure = FailureCause.from_error(fields.get("error") or fields.get("cause") or event.replace(".", "_"))
    try:
        item = sink.record(event, failure=failure.payload() if failure else None, **fields)
        if isinstance(item, RuntimeEvent) and failure is not None:
            reference = (item.fields.get("failure") or {}).get("evidence_ref")
            if reference:
                return replace(failure, evidence_ref=reference)
    except Exception:
        pass
    return failure
