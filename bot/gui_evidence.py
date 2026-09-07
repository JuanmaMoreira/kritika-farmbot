"""Explicit, best-effort local evidence access; independent of Tk and workers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import url2pathname

from bot.session_report import ReportStatus, SessionReport


def report_evidence_refs(report: SessionReport | None) -> tuple[str, ...]:
    if report is None:
        return ()
    nodes = [report]
    for character in report.characters:
        nodes.append(character)
        nodes.extend(character.flows)
    return tuple(dict.fromkeys(
        node.failure.evidence_ref for node in nodes
        if node.status is ReportStatus.TECHNICAL_FAILURE
        and node.failure is not None and node.failure.evidence_ref
    ))


def _open_directory(path: Path) -> None:
    os.startfile(str(path), "explore")


def locate_evidence(reference: str, *, opener: Callable[[Path], None] = _open_directory) -> str:
    """Check availability at click time, then locate the bundle, never execute it."""
    try:
        uri = urlsplit(reference)
        if uri.scheme != "file" or uri.netloc or uri.query or uri.fragment:
            return "Evidence unavailable: expected a local file reference."
        decoded = url2pathname(uri.path)
        if decoded.startswith(("\\\\", "//")):
            return "Evidence unavailable: expected a local file reference."
        path = Path(decoded)
        if not path.is_absolute() or path.name != "failure.json" or not path.is_file():
            return "Evidence unavailable or expired."
        path = path.resolve(strict=True)
        if str(path).startswith(("\\\\", "//")):
            return "Evidence unavailable: expected a local file reference."
        opener(path.parent)
        return f"Evidence folder: {path.parent}"
    except Exception:
        # Retention may remove a bundle between the check and the open action.
        return "Evidence unavailable or could not be opened."
