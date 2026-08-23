"""Interactive batch screenshots backed by the 0.2 frame source.

The module is import-safe. Configuration, external processes, windows and
filesystem writes are created only from ``main()``.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.adb import AdbError
from bot.capture import CaptureError
from bot.config import RuntimeConfig
from bot.runtime import build_frame_source

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "screencaps" / "batch"
WINDOW = "Batch Screencap  |  [SPACE] Capturar  [Q] Salir"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview the 0.2 scrcpy stream and save selected frames."
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="dotenv file to load explicitly (default: project .env)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for selected PNG frames",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        source = build_frame_source(config)
        args.output.mkdir(parents=True, exist_ok=True)
        print("Conectando mediante el runtime 0.2...")
        with source:
            print(f"Listo. Las capturas se guardan en: {args.output}")
            print("[SPACE] Capturar frame  |  [Q] Salir")
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

            while True:
                frame = source.get_frame().image
                cv2.imshow(WINDOW, frame)
                key = cv2.waitKey(50) & 0xFF

                if key in (ord("q"), ord("Q")):
                    break
                if key == ord(" "):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    path = args.output / f"{timestamp}.png"
                    cv2.imwrite(str(path), frame)
                    print(f"[+] Guardado: {path.name}")

                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
    except KeyboardInterrupt:
        print("Captura interrumpida; recursos liberados.", file=sys.stderr)
        return 130
    except (AdbError, CaptureError, ValueError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
