"""Isolated passive HIL measurement; no input, OCR, resolver or gameplay policy.

One source, bounded lifetime, operator stop file. Retains periodic representatives
and onset of visually static windows; thumbnail differences are diagnostics only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np

from bot.config import RuntimeConfig
from bot.runtime import build_adb_client, build_frame_source

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=1200)
    parser.add_argument('--native-label')
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT)
    if not 0 < args.duration <= 1800:
        parser.error('duration must be in (0, 1800]')
    output.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_env(dotenv_path=ROOT / '.env')
    adb = build_adb_client(config)
    if args.native_label:
        if not args.native_label.replace('-', '').isalnum():
            parser.error('native label must be alphanumeric with optional hyphens')
        started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        tick = time.perf_counter()
        png = adb.capture_png()
        seconds = time.perf_counter() - tick
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Invalid native PNG')
        path = output / f'{args.native_label}-{time.time_ns()}.png'
        path.write_bytes(png)
        h, w = image.shape[:2]
        record = dict(path=path.relative_to(ROOT).as_posix(), source='native_adb',
                      captured_at_utc=started_utc, sequence_scope='native_single',
                      source_sequence=None, width=w, height=h, capture_s=seconds,
                      sha256=hashlib.sha256(png).hexdigest(), label=args.native_label)
        with (output / 'native.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record) + '\n')
        print(json.dumps(record))
        return
    stop = output / 'STOP'
    if stop.exists():
        parser.error('STOP already exists; use a fresh output directory')
    started = time.monotonic()
    last_keep = last_preview = last_log = -float('inf')
    previous = None
    static_count = 0
    sequence = None
    with (output / 'measurements.jsonl').open('a', encoding='utf-8') as log:
        with build_frame_source(config, adb_client=adb, max_fps=10) as source:
            while time.monotonic() - started < args.duration and not stop.exists():
                tick = time.monotonic()
                snapshot = source.get_frame()
                capture_ms = (time.monotonic() - tick) * 1000
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                image = snapshot.image
                h, w = image.shape[:2]
                analysis = time.monotonic()
                thumb = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (96, 44))
                difference = None if previous is None else float(np.mean(np.abs(
                    thumb.astype(np.float32) - previous.astype(np.float32))) / 255)
                fresh = snapshot.sequence != sequence
                static_count = static_count + 1 if difference is not None and difference < .012 else 0
                analysis_ms = (time.monotonic() - analysis) * 1000
                record = dict(captured_at_utc=now, source_sequence=snapshot.sequence,
                              source='live_scrcpy', width=w, height=h,
                              elapsed_s=tick-started, get_frame_ms=capture_ms,
                              analysis_ms=analysis_ms, frame_age_s=tick-snapshot.timestamp,
                              new_sequence=fresh, thumbnail_difference=difference)
                if tick-last_keep >= 20 or static_count == 3:
                    path = output / f'frame_{snapshot.sequence}_{time.time_ns()}.png'
                    io_start = time.monotonic()
                    if not cv2.imwrite(str(path), image):
                        raise OSError(path)
                    record.update(path=path.relative_to(ROOT).as_posix(),
                                  sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  png_io_ms=(time.monotonic()-io_start)*1000,
                                  retention='periodic_or_static_onset_not_semantic')
                    last_keep = tick
                if tick-last_preview >= 5:
                    cv2.imwrite(str(output / 'latest.png'), image)
                    (output / 'latest.json').write_text(json.dumps(record), encoding='utf-8')
                    last_preview = tick
                log.write(json.dumps(record) + '\n')
                log.flush()
                if tick-last_log >= 30:
                    print(json.dumps(record), flush=True)
                    last_log = tick
                previous, sequence = thumb, snapshot.sequence
                time.sleep(max(0, 1-(time.monotonic()-tick)))
    print(json.dumps({'stopped': True, 'elapsed_s': time.monotonic()-started}), flush=True)


if __name__ == '__main__':
    main()
