"""Compare Auto Battle temporal activity across human-confirmed reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import cv2
import numpy as np

from bot.auto_battle import AutoBattleCalibration, measure_auto_battle_activities


DEFAULT_ROIS = (
    (0.8278, 0.0098, 0.9329, 0.0981),
    (0.8278, 0.0098, 0.8950, 0.0880),
    (0.8320, 0.0140, 0.8920, 0.0820),
    (0.8350, 0.0180, 0.8900, 0.0780),
)


def evaluate(report_path: Path, roi):
    calibration = AutoBattleCalibration(roi=roi)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    results = []
    for record in payload["records"]:
        frames = tuple(cv2.imread(item["frame_path"]) for item in record["evidence"])
        if any(frame is None for frame in frames):
            raise FileNotFoundError("an evidence frame could not be read")
        activities = measure_auto_battle_activities(frames, calibration)[1:]
        results.append(
            {
                "mean": float(np.mean(activities)),
                "median": float(np.median(activities)),
                "p25": float(np.percentile(activities, 25)),
                "maximum": float(np.max(activities)),
            }
        )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("off_report", type=Path)
    parser.add_argument("on_report", type=Path)
    args = parser.parse_args(argv)
    for roi in DEFAULT_ROIS:
        print(
            json.dumps(
                {
                    "roi": roi,
                    "off": evaluate(args.off_report, roi),
                    "on": evaluate(args.on_report, roi),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
