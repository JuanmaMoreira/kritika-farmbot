from types import SimpleNamespace

import numpy as np
import pytest

from bot.ocr import OcrEngineError, OcrResult, RapidOcrEngine


class Backend:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def __call__(self, image, **kwargs):
        self.calls.append((image.copy(), kwargs))
        return self.output


def test_rapid_ocr_engine_returns_text_confidence_and_metadata():
    backend = Backend(SimpleNamespace(txts=("01:30",), scores=(0.92,)))
    engine = RapidOcrEngine(backend_factory=lambda: backend)

    result = engine.recognize(np.zeros((24, 80, 3), dtype=np.uint8))

    assert result == OcrResult(
        text="01:30",
        confidence=0.92,
        metadata=(("backend", "rapidocr"), ("line_count", 1)),
    )
    assert backend.calls[0][1] == {
        "use_det": False,
        "use_cls": False,
        "use_rec": True,
    }


def test_rapid_ocr_engine_represents_empty_output_without_default_text():
    engine = RapidOcrEngine(
        backend_factory=lambda: Backend(SimpleNamespace(txts=(), scores=()))
    )

    result = engine.recognize(np.zeros((10, 10), dtype=np.uint8))

    assert result.text == ""
    assert result.confidence == 0.0
    assert ("line_count", 0) in result.metadata


def test_rapid_ocr_engine_wraps_backend_errors():
    def fail():
        raise RuntimeError("model unavailable")

    engine = RapidOcrEngine(backend_factory=fail)

    with pytest.raises(OcrEngineError, match="initialization failed"):
        engine.recognize(np.zeros((10, 10), dtype=np.uint8))


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), True])
def test_ocr_result_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        OcrResult("5", confidence)
