"""Stepwise live directed-scroll smoke for Trading Center materials.

Every command is short-lived and performs at most one physical gesture,
so each swipe is its own authorized action. Row titles arrive through
explicit per-observation sidecar files (the operator owns row identity
until an OCR reader exists): a command that needs titles saves a list
crop and exits 3 naming the ``rows_<seq>.json`` file to write; the
operator views the crop, writes one catalog id per band top to bottom,
and re-invokes. Subcommands:

- ``plan``: capture, gate (General + material rows), resolve titles,
  then either run target consensus (fresh captures, same titles) or
  print the planned gesture. No input beyond capture.
- ``swipe``: execute one planned gesture, settle, capture the landing
  viewport and print its bands (or request titles first).
- ``verify``: pure progress check between two viewport states.

Swipe gestures go through ``AdbClient.swipe`` only; this tool contains
no tap path by construction.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.adb import AdbError
from bot.config import RuntimeConfig
from bot.directed_list_scroll import (
    DirectedScrollOutcome,
    plan_directed_gesture,
    range_progressed,
)
from bot.observations import ObservationBatch
from bot.perception.local_cv import LocalCvDetector
from bot.perception.trading_center import (
    TRADING_CENTER_TITLE_SPEC,
    TradingRowsDetector,
    TradingTabsDetector,
    row_bands,
)
from bot.runtime import build_adb_client
from bot.state import ResolvedState, ResolutionStatus
from bot.trading_center import TradingTab, trading_tab
from bot.trading_center_semantics import SCREEN_TRADING
from bot.trading_materials_scroll import (
    MATERIAL_CATALOG,
    TRADING_MATERIALS_SCROLL_PROFILE,
    MaterialRow,
    MaterialViewport,
    viewport_to_reading,
)

EXIT_NEED_TITLES = 3


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotenv", type=Path, default=REPOSITORY_ROOT / ".env")
    parser.add_argument("--workdir", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="capture, gate and plan or consensus")
    plan.add_argument("--target", required=True)
    plan.add_argument("--remaining", type=int, required=True)
    plan.add_argument(
        "--live",
        action="store_true",
        help="acknowledge physical device access (capture only)",
    )

    swipe = sub.add_parser("swipe", help="execute one planned gesture")
    swipe.add_argument("--gesture", default=None,
                       help="gesture JSON printed by plan")
    swipe.add_argument("--gesture-file", type=Path, default=None,
                       help="read the gesture JSON from a file")
    swipe.add_argument("--settle", type=float, default=1.5)
    swipe.add_argument("--duration-ms", type=int, default=900)
    swipe.add_argument("--settle-burst", action="store_true",
                       help="save extra frames while the list settles")
    swipe.add_argument(
        "--live",
        action="store_true",
        help="acknowledge the physical swipe",
    )

    verify = sub.add_parser("verify", help="pure progress check")
    verify.add_argument("--direction", required=True, choices=("forward", "backward"))
    verify.add_argument("--pre", required=True, help="pre viewport JSON")
    verify.add_argument("--post", required=True, help="post viewport JSON")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("plan", "swipe") and not args.live:
        print(
            "Refusing device access without --live. "
            "Obtain the required chat authorization first.",
            file=sys.stderr,
        )
        return 2
    workdir = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
    except (AdbError, OSError, ValueError) as error:
        print(f"ADB setup failed: {error}", file=sys.stderr)
        return 2
    adb_binary = str(config.adb_executable)
    serial = str(config.device_serial)

    title = LocalCvDetector(TRADING_CENTER_TITLE_SPEC, asset_root=REPOSITORY_ROOT)
    tabs = TradingTabsDetector(asset_root=REPOSITORY_ROOT)
    rows_detector = TradingRowsDetector(asset_root=REPOSITORY_ROOT)
    session = SmokeSession(
        adb, adb_binary, serial, title, tabs, rows_detector, workdir
    )
    if args.command == "plan":
        return session.plan(args.target, args.remaining)
    if args.command == "swipe":
        gesture_json = args.gesture
        if args.gesture_file is not None:
            gesture_json = args.gesture_file.read_text(encoding="utf-8")
        if not gesture_json:
            print("swipe needs --gesture or --gesture-file", file=sys.stderr)
            return 2
        return session.swipe(gesture_json, args.settle, args.duration_ms,
                             args.settle_burst)
    if args.command == "verify":
        return session.verify(args.direction, args.pre, args.post)
    return 2


class SmokeSession:
    def __init__(self, adb, adb_binary, serial, title, tabs, rows_detector,
                 workdir):
        self.adb = adb
        self.adb_binary = adb_binary
        self.serial = serial
        self.title = title
        self.tabs = tabs
        self.rows_detector = rows_detector
        self.workdir = workdir
        self.sequence = self._last_sequence()

    def _last_sequence(self) -> int:
        frames = sorted(self.workdir.glob("frame_*.png"))
        if not frames:
            return 0
        return max(int(path.stem.split("_")[1]) for path in frames)

    def _run_pull(self, remote: str, local: Path) -> None:
        completed = subprocess.run(
            [self.adb_binary, "-s", self.serial, "pull", remote, str(local)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"adb pull failed: {completed.stderr}")

    def capture(self, tag: str):
        self.sequence += 1
        sequence = self.sequence
        self.adb.shell("screencap", "-p", "/sdcard/hil_smoke.png", timeout=30)
        local = self.workdir / f"frame_{sequence:03d}_{tag}.png"
        self._run_pull("/sdcard/hil_smoke.png", local)
        frame = cv2.imread(str(local))
        if frame is None:
            raise RuntimeError(f"undecodable capture: {local}")
        height, width = frame.shape[:2]
        return sequence, frame, height, width

    def detect(self, frame):
        return (
            *self.title.detect(frame),
            *self.tabs.detect(frame),
            *self.rows_detector.detect(frame),
        )

    def snapshot(self, frame, sequence):
        names = {observation.name for observation in self.detect(frame)}
        if "landmark.trading_center_title" not in names:
            return None
        return FakeSnapshot(sequence, self.detect(frame))

    def gate(self, frame, sequence):
        names = {observation.name for observation in self.detect(frame)}
        if "indicator.trading_material_rows" not in names:
            return "materials rows not detected"
        resolved = self.snapshot(frame, sequence)
        if resolved is None or trading_tab(resolved) is not TradingTab.GENERAL:
            return "General tab not active"
        return None

    def titles_for(self, sequence, frame, bands):
        titles_path = self.workdir / f"rows_{sequence:03d}.json"
        if not titles_path.is_file():
            reused = self.reuse_titles(sequence, bands)
            if reused is not None:
                return reused
            self.save_crop(sequence, frame, bands)
            print(f"need titles: write {titles_path.name}", flush=True)
            return None
        try:
            payload = json.loads(titles_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            print(f"need titles: rewrite {titles_path.name}", flush=True)
            return None
        pairs = self.parse_titles(payload, titles_path.name, len(bands))
        return pairs

    def reuse_titles(self, sequence, bands):
        """Adopt the latest titles file from the current position epoch.

        Centers are grid-stable within ~0.002 at a fixed list position; a
        0.01 tolerance only matches across commands when nothing moved. A
        gesture advances the epoch (same fractional phase can recur with
        different content), so only files written after the last executed
        gesture are eligible. Manual list motion between commands is
        forbidden by the smoke protocol.
        """
        epoch_path = self.workdir / "last_gesture_seq.json"
        epoch = -1
        if epoch_path.is_file():
            try:
                epoch = int(json.loads(epoch_path.read_text(
                    encoding="utf-8"))["sequence"])
            except (ValueError, OSError, KeyError):
                pass
        candidates = sorted(self.workdir.glob("rows_*.json"))
        for path in reversed(candidates):
            try:
                own = int(path.stem.split("_")[1])
            except (ValueError, IndexError):
                continue
            if own >= sequence or own <= epoch:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            pairs = self.parse_titles(payload, path.name, len(bands))
            if pairs is None:
                continue
            try:
                need = json.loads(
                    (self.workdir / f"need_{own:03d}.json").read_text(
                        encoding="utf-8"
                    )
                )
                old_centers = [band["center"] for band in need["bands"]]
            except (ValueError, OSError, KeyError):
                continue
            if len(old_centers) != len(bands):
                continue
            if all(
                abs(new[2] - old) <= 0.01
                for new, old in zip(bands, old_centers)
            ):
                print(f"reusing titles from {path.name}", flush=True)
                return pairs
        return None

    @staticmethod
    def parse_titles(payload, name, band_count):
        mapping = payload.get("titles")
        if not isinstance(mapping, dict):
            print(f"need titles: fix {name}", flush=True)
            return None
        try:
            pairs = [(int(index), mapping[str(index)]) for index in mapping]
        except (ValueError, KeyError):
            print(f"need titles: fix {name}", flush=True)
            return None
        if (
            any(index < 0 or index >= band_count for index, _ in pairs)
            or any(not isinstance(row_id, str) or not row_id
                   for _, row_id in pairs)
            or len({index for index, _ in pairs}) != len(pairs)
        ):
            print(f"need titles: fix {name}", flush=True)
            return None
        return sorted(pairs)

    def save_crop(self, sequence, frame, bands):
        height, width = frame.shape[:2]
        crop = frame[int(0.30 * height):int(0.97 * height),
                     int(0.20 * width):int(0.62 * width)]
        ch, cw = crop.shape[:2]
        for index, (top, bottom, center, complete) in enumerate(bands):
            y1 = int((top - 0.30) / 0.67 * ch)
            y2 = int((bottom - 0.30) / 0.67 * ch)
            color = (0, 255, 0) if complete else (0, 165, 255)
            cv2.rectangle(crop, (4, y1), (cw - 4, y2), color, 3)
            cv2.putText(crop, str(index), (12, y1 + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)
        view = cv2.resize(crop, (520, int(520 * crop.shape[0] / crop.shape[1])))
        crop_name = f"rows_{sequence:03d}.png"
        cv2.imwrite(str(self.workdir / crop_name), view)
        need = {
            "sequence": sequence,
            "crop": crop_name,
            "bands": [
                {"index": index, "top": top, "bottom": bottom,
                 "center": center, "complete": complete}
                for index, (top, bottom, center, complete) in enumerate(bands)
            ],
            "instruction": (
                f"write rows_{sequence:03d}.json with "
                '{"titles": {<band index>: <MATERIAL_CATALOG id>}} '
                "for bands showing rows only; skip padding bands"
            ),
        }
        (self.workdir / f"need_{sequence:03d}.json").write_text(
            json.dumps(need, indent=2), encoding="utf-8"
        )

    def viewport_state(self, sequence, bands, pairs):
        return {
            "sequence": sequence,
            "rows": [
                {"id": row_id, "center": bands[index][2],
                 "complete": bands[index][3]}
                for index, row_id in pairs
            ],
        }

    def viewport_for(self, bands, pairs, sequence):
        return MaterialViewport(
            rows=tuple(
                MaterialRow(row_id=row_id, center_y=bands[index][2],
                            complete=bands[index][3])
                for index, row_id in pairs
            ),
            sequence=sequence,
            readable=True,
            guard_ok=True,
        )

    def plan(self, target: str, remaining: int) -> int:
        if target not in MATERIAL_CATALOG:
            print(f"unknown target: {target}", file=sys.stderr)
            return 2
        sequence, frame, _, _ = self.capture("plan")
        problem = self.gate(frame, sequence)
        if problem is not None:
            print(f"gate failed: {problem}", file=sys.stderr)
            return 1
        bands = row_bands(frame)
        pairs = self.titles_for(sequence, frame, bands)
        if pairs is None:
            return EXIT_NEED_TITLES
        reading = viewport_to_reading(
            self.viewport_for(bands, pairs, sequence),
            target=target,
        )
        if target in reading.visible_ids:
            return self.consensus(target, reading)
        if remaining <= 0:
            print(json.dumps({"outcome": "budget_exhausted",
                              "state": self.viewport_state(sequence, bands,
                                                           pairs)}))
            return 1
        gesture = plan_directed_gesture(
            catalog=MATERIAL_CATALOG,
            target=target,
            visible_ids=reading.visible_ids,
            profile=TRADING_MATERIALS_SCROLL_PROFILE,
        )
        print(json.dumps({
            "outcome": "plan",
            "gesture": {
                "direction": gesture.direction.value,
                "rows": gesture.rows,
                "delta": gesture.delta,
                "lane_x": gesture.lane_x,
                "start_y": gesture.start_y,
                "end_y": gesture.end_y,
            },
            "state": self.viewport_state(sequence, bands, pairs),
        }))
        return 0

    def consensus(self, target, reading) -> int:
        first_y = reading.target_row_y
        last_y, last_sequence = first_y, reading.sequence
        agreements = 1
        profile = TRADING_MATERIALS_SCROLL_PROFILE
        for _ in range(1, profile.consensus_max_samples):
            sequence, frame, _, _ = self.capture("consensus")
            problem = self.gate(frame, sequence)
            if problem is not None:
                print(json.dumps({"outcome": "guard_or_readability_lost",
                                  "detail": problem}))
                return 1
            bands = row_bands(frame)
            pairs = self.titles_for(sequence, frame, bands)
            if pairs is None:
                return EXIT_NEED_TITLES
            if sequence <= last_sequence:
                print(json.dumps({"outcome": "stale_sample"}))
                return 1
            last_sequence = sequence
            sample = viewport_to_reading(
                self.viewport_for(bands, pairs, sequence),
                target=target,
            )
            if (
                target not in sample.visible_ids
                or sample.target_row_y is None
                or abs(sample.target_row_y - last_y) > profile.row_tolerance
            ):
                print(json.dumps({"outcome": "target_unstable"}))
                return 1
            agreements += 1
            last_y = sample.target_row_y
            if agreements >= profile.consensus_required:
                print(json.dumps({
                    "outcome": str(DirectedScrollOutcome.TARGET_READY.value),
                    "stable_row_y": last_y,
                    "stable_sequence": sequence,
                }))
                return 0
        print(json.dumps({"outcome": "target_unstable"}))
        return 1

    def swipe(self, gesture_json: str, settle: float, duration_ms: int,
              burst: bool = False) -> int:
        try:
            gesture = json.loads(gesture_json)
            lane_x = float(gesture["lane_x"])
            start_y = float(gesture["start_y"])
            end_y = float(gesture["end_y"])
        except (ValueError, KeyError, TypeError) as error:
            print(f"invalid gesture: {error}", file=sys.stderr)
            return 2
        if duration_ms < 1 or settle < 0:
            print("duration-ms/settle out of range", file=sys.stderr)
            return 2
        sequence, frame, height, width = self.capture("pre_swipe")
        (self.workdir / "last_gesture_seq.json").write_text(
            json.dumps({"sequence": sequence}), encoding="utf-8"
        )
        x = int(lane_x * width)
        y1 = int(start_y * height)
        y2 = int(end_y * height)
        self.adb.swipe(x, y1, x, y2, duration_ms, timeout=60)
        print(json.dumps({"gesture": "executed",
                          "pixels": {"x": x, "y1": y1, "y2": y2,
                                     "duration_ms": duration_ms}}),
              flush=True)
        if burst:
            for delay, tag in ((0.4, "settle04"), (0.9, "settle09")):
                time.sleep(delay)
                self.capture(tag)
            time.sleep(max(0.0, settle - 1.3))
        else:
            time.sleep(settle)
        sequence, frame, _, _ = self.capture("landed")
        problem = self.gate(frame, sequence)
        if problem is not None:
            print(json.dumps({"outcome": "gate_lost_after_gesture",
                              "detail": problem}))
            return 1
        bands = row_bands(frame)
        pairs = self.titles_for(sequence, frame, bands)
        if pairs is None:
            return EXIT_NEED_TITLES
        print(json.dumps({
            "outcome": "landed",
            "state": self.viewport_state(sequence, bands, pairs),
        }))
        return 0

    def verify(self, direction: str, pre_json: str, post_json: str) -> int:
        try:
            pre_path, post_path = Path(pre_json), Path(post_json)
            pre = json.loads(pre_path.read_text(encoding="utf-8")
                             if pre_path.is_file() else pre_json)
            post = json.loads(post_path.read_text(encoding="utf-8")
                              if post_path.is_file() else post_json)
        except ValueError as error:
            print(f"invalid state: {error}", file=sys.stderr)
            return 2
        pre_ids = [row["id"] for row in pre["rows"]]
        post_ids = [row["id"] for row in post["rows"]]
        catalog = list(MATERIAL_CATALOG)
        try:
            pre_range = (catalog.index(pre_ids[0]), catalog.index(pre_ids[-1]))
            post_range = (catalog.index(post_ids[0]), catalog.index(post_ids[-1]))
        except (ValueError, IndexError) as error:
            print(f"unmapped ids: {error}", file=sys.stderr)
            return 2
        from bot.directed_list_scroll import ScrollDirection

        progressed = range_progressed(
            direction=(ScrollDirection.FORWARD if direction == "forward"
                       else ScrollDirection.BACKWARD),
            pre_first=pre_range[0],
            pre_last=pre_range[1],
            post_first=post_range[0],
            post_last=post_range[1],
        )
        print(json.dumps({
            "progressed": progressed,
            "pre_range": pre_range,
            "post_range": post_range,
        }))
        return 0 if progressed else 1


class FakeSnapshot:
    def __init__(self, sequence, observations):
        self.observations = ObservationBatch(
            sequence, float(sequence), tuple(observations)
        )
        self.state = ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=SCREEN_TRADING,
            overlays=(),
        )


if __name__ == "__main__":
    raise SystemExit(main())
