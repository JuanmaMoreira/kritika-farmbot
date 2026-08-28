"""Small backend-neutral OCR boundary with a local RapidOCR implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Protocol

import numpy as np


OcrMetadataValue = str | int | float | bool


@dataclass(frozen=True)
class OcrResult:
    """Text recognized from one prepared image, plus diagnostic evidence."""

    text: str
    confidence: float
    metadata: tuple[tuple[str, OcrMetadataValue], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, Real
        ):
            raise ValueError("confidence must be a real number in [0, 1]")
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        metadata = tuple(self.metadata)
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, (str, int, float, bool))
            for key, value in metadata
        ):
            raise ValueError("metadata must contain named scalar diagnostics")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "metadata", metadata)


class OcrEngine(Protocol):
    """Recognize text from an already-cropped and prepared image."""

    def recognize(self, image: np.ndarray) -> OcrResult: ...


class OcrEngineError(RuntimeError):
    """A local OCR backend could not initialize or execute."""


RapidOcrFactory = Callable[[], object]


class RapidOcrEngine:
    """Lazy CPU/offline OCR backed by the packaged RapidOCR ONNX models."""

    def __init__(self, *, backend_factory: RapidOcrFactory | None = None) -> None:
        self._backend_factory = backend_factory or _build_rapidocr
        self._backend: object | None = None

    def recognize(self, image: np.ndarray) -> OcrResult:
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("image must be a non-empty NumPy array")
        if image.ndim not in (2, 3):
            raise ValueError("image must be grayscale or color")

        try:
            backend = self._backend_instance()
            output = backend(
                image,
                use_det=False,
                use_cls=False,
                use_rec=True,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            raise OcrEngineError(f"RapidOCR recognition failed: {error}") from error

        texts = tuple(str(text) for text in (getattr(output, "txts", ()) or ()))
        scores = tuple(float(score) for score in (getattr(output, "scores", ()) or ()))
        if not texts:
            return OcrResult(
                text="",
                confidence=0.0,
                metadata=(("backend", "rapidocr"), ("line_count", 0)),
            )
        if len(scores) != len(texts) or any(
            not math.isfinite(score) or not 0.0 <= score <= 1.0
            for score in scores
        ):
            raise OcrEngineError("RapidOCR returned invalid confidence data")

        return OcrResult(
            text=" ".join(texts),
            confidence=sum(scores) / len(scores),
            metadata=(("backend", "rapidocr"), ("line_count", len(texts))),
        )

    def _backend_instance(self):
        if self._backend is None:
            try:
                self._backend = self._backend_factory()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                raise OcrEngineError(
                    f"RapidOCR initialization failed: {error}"
                ) from error
        if not callable(self._backend):
            raise OcrEngineError("RapidOCR backend must be callable")
        return self._backend


def _build_rapidocr():
    try:
        from rapidocr import RapidOCR
    except ImportError as error:
        raise OcrEngineError(
            "RapidOCR is unavailable; install the pinned OCR requirements"
        ) from error
    return RapidOCR(params={"Global.log_level": "critical"})


__all__ = ("OcrEngine", "OcrEngineError", "OcrResult", "RapidOcrEngine")
