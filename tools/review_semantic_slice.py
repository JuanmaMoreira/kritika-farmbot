"""Interactive OpenCV review UI for semantic-slice ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from bot.catalog import (
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_BLACK_MARKET,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
)
from tools.semantic_slice_evaluation import (
    CONFIRMED,
    EVALUATION_VERSION,
    ManifestEntry,
    ReviewCandidate,
    SKIPPED,
    UNKNOWN_BASE_CONTEXT,
    UNSURE,
    load_manifest,
    validate_relative_path,
    write_manifest,
)

BASE_KEYS = {
    ord("1"): SCREEN_LOBBY,
    ord("2"): SCREEN_CHARACTER_SELECT,
    ord("3"): SCREEN_BATTLE_MODE_SELECT,
    ord("4"): SCREEN_BLACK_MARKET,
    ord("0"): UNKNOWN_BASE_CONTEXT,
}


def load_review_candidates(path: str | Path) -> tuple[ReviewCandidate, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != EVALUATION_VERSION:
        raise ValueError("unsupported review selection version")
    candidates = []
    for item in payload.get("candidates", ()):
        candidates.append(
            ReviewCandidate(
                path=validate_relative_path(item["path"]),
                reasons=tuple(item.get("reasons", ())),
                scores=tuple(
                    (str(name), float(score))
                    for name, score in item.get("scores", ())
                ),
            )
        )
    return tuple(candidates)


def review(
    repository_root: str | Path,
    selection_path: str | Path,
    manifest_path: str | Path,
) -> None:
    repository_root = Path(repository_root).resolve()
    candidates = load_review_candidates(selection_path)
    entries = {entry.path: entry for entry in load_manifest(manifest_path)}

    print("Keys: 1 lobby, 2 character select, 3 battle-mode select, 4 black market")
    print("      0 unknown, p toggle purchase popup, Enter confirm")
    print("      u unsure, s skipped, q save and quit")

    for index, candidate in enumerate(candidates, start=1):
        frame = cv2.imread(
            str(repository_root / candidate.path), cv2.IMREAD_COLOR
        )
        if frame is None:
            print(f"[WARN] unreadable: {candidate.path}")
            entries[candidate.path] = ManifestEntry(
                candidate.path, None, (), SKIPPED
            )
            continue

        existing = entries.get(candidate.path)
        base_context = (
            existing.base_context
            if existing is not None and existing.review_status == CONFIRMED
            else None
        )
        purchase_overlay = bool(
            existing is not None
            and POPUP_PURCHASE_CONFIRMATION in existing.overlays
        )

        while True:
            display = _review_frame(
                frame,
                candidate,
                index,
                len(candidates),
                base_context,
                purchase_overlay,
            )
            cv2.imshow("Kritika semantic slice review", display)
            key = cv2.waitKeyEx(0) & 0xFF
            if key in BASE_KEYS:
                base_context = BASE_KEYS[key]
                continue
            if key == ord("p"):
                purchase_overlay = not purchase_overlay
                continue
            if key in (10, 13) and base_context is not None:
                overlays = (
                    (POPUP_PURCHASE_CONFIRMATION,)
                    if purchase_overlay
                    else ()
                )
                entries[candidate.path] = ManifestEntry(
                    candidate.path, base_context, overlays, CONFIRMED
                )
                break
            if key == ord("u"):
                entries[candidate.path] = ManifestEntry(
                    candidate.path, None, (), UNSURE
                )
                break
            if key == ord("s"):
                entries[candidate.path] = ManifestEntry(
                    candidate.path, None, (), SKIPPED
                )
                break
            if key == ord("q"):
                write_manifest(manifest_path, entries.values())
                cv2.destroyAllWindows()
                return

        write_manifest(manifest_path, entries.values())

    cv2.destroyAllWindows()


def _review_frame(
    frame,
    candidate: ReviewCandidate,
    index: int,
    total: int,
    base_context: str | None,
    purchase_overlay: bool,
):
    target_width = min(frame.shape[1], 1500)
    scale = target_width / frame.shape[1]
    display = cv2.resize(
        frame,
        (target_width, round(frame.shape[0] * scale)),
        interpolation=cv2.INTER_AREA,
    )
    lines = [
        f"{index}/{total} {candidate.path}",
        f"base={base_context or '<choose>'}",
        f"purchase_overlay={purchase_overlay}",
        "reasons=" + ", ".join(candidate.reasons),
    ]
    lines.extend(f"{name}={score:.4f}" for name, score in candidate.scores)
    for line_index, text in enumerate(lines):
        y = 30 + line_index * 27
        cv2.putText(
            display,
            text,
            (15, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            display,
            text,
            (15, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return display


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--selection",
        default="artifacts/semantic_slice/review_selection.json",
    )
    parser.add_argument(
        "--manifest", default="datasets/semantic_slice_manifest.json"
    )
    arguments = parser.parse_args(argv)
    review(arguments.repo_root, arguments.selection, arguments.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
