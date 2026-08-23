from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import sys

import pytest

from bot.observations import Observation, ObservationBatch, ObservationSource


def observation(**overrides):
    values = {
        "name": "screen.lobby",
        "confidence": 0.85,
        "source": ObservationSource.LOCAL_CV,
    }
    values.update(overrides)
    return Observation(**values)


def test_valid_observation_has_semantic_fields():
    item = observation(value=True, region=[0.1, 0.2, 0.4, 0.6])

    assert item.name == "screen.lobby"
    assert item.confidence == 0.85
    assert item.source is ObservationSource.LOCAL_CV
    assert item.value is True
    assert item.region == (0.1, 0.2, 0.4, 0.6)


@pytest.mark.parametrize(
    "name",
    ["screen.lobby", "popup.daily_reward", "element.close-button", "stamina.current"],
)
def test_accepts_namespaced_semantic_names(name):
    assert observation(name=name).name == name


@pytest.mark.parametrize(
    "name", ["", "lobby", "Screen.lobby", ".screen", "screen.", "screen..lobby", 7]
)
def test_rejects_invalid_semantic_names(name):
    with pytest.raises(ValueError, match="namespaced"):
        observation(name=name)


@pytest.mark.parametrize("confidence", [0.0, 0.37, 1.0])
def test_accepts_normalized_confidence_boundaries_and_middle(confidence):
    assert observation(confidence=confidence).confidence == confidence


@pytest.mark.parametrize(
    "confidence", [-0.01, 1.01, float("nan"), float("inf"), float("-inf"), True]
)
def test_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        observation(confidence=confidence)


@pytest.mark.parametrize("value", [None, False, True, 37, 12.5, "ready"])
def test_accepts_supported_semantic_values(value):
    assert observation(value=value).value == value


@pytest.mark.parametrize("value", [object(), [1], {"count": 2}, float("nan")])
def test_rejects_non_semantic_values(value):
    with pytest.raises(ValueError, match="value"):
        observation(value=value)


@pytest.mark.parametrize(
    "region",
    [
        (-0.01, 0.0, 1.0, 1.0),
        (0.0, 0.0, 1.01, 1.0),
        (0.8, 0.0, 0.2, 1.0),
        (0.0, 0.5, 1.0, 0.5),
        (0.0, 0.0, float("nan"), 1.0),
    ],
)
def test_rejects_invalid_relative_regions(region):
    with pytest.raises(ValueError):
        observation(region=region)


@pytest.mark.parametrize("source", list(ObservationSource))
def test_accepts_every_declared_source(source):
    assert observation(source=source).source is source


@pytest.mark.parametrize("source", ["local_cv", "gpt_5", None])
def test_rejects_non_enum_sources(source):
    with pytest.raises(ValueError, match="source"):
        observation(source=source)


def test_observation_is_immutable():
    item = observation()

    with pytest.raises(FrozenInstanceError):
        item.confidence = 0.1


def test_empty_batch_is_valid_and_preserves_frame_identity():
    batch = ObservationBatch(sequence=4, timestamp=123.5)

    assert batch.sequence == 4
    assert batch.timestamp == 123.5
    assert batch.observations == ()


def test_batch_preserves_multiple_observations_and_duplicate_names():
    local = observation(confidence=0.82, source=ObservationSource.LOCAL_CV)
    vlm = observation(confidence=0.95, source=ObservationSource.VLM)
    element = observation(name="element.claim", confidence=0.9)

    batch = ObservationBatch(1, 10.0, [local, vlm, element])

    assert batch.observations == (local, vlm, element)
    assert batch.find("screen.lobby") == (local, vlm)
    assert batch.best("screen.lobby") is vlm
    assert batch.find("popup.reward") == ()
    assert batch.best("popup.reward") is None


@pytest.mark.parametrize(
    ("sequence", "timestamp"),
    [(-1, 1.0), (True, 1.0), (1, -0.1), (1, float("nan")), (1, float("inf"))],
)
def test_batch_rejects_invalid_frame_identity(sequence, timestamp):
    with pytest.raises(ValueError):
        ObservationBatch(sequence, timestamp)


def test_batch_rejects_non_observations():
    with pytest.raises(ValueError, match="Observation"):
        ObservationBatch(1, 1.0, [observation(), "screen.lobby"])


def test_batch_and_its_collection_are_immutable():
    batch = ObservationBatch(1, 1.0, [observation()])

    assert isinstance(batch.observations, tuple)
    with pytest.raises(FrozenInstanceError):
        batch.sequence = 2


def test_semantic_contract_modules_import_without_perception_dependencies(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import bot.observations; import bot.state; "
                "assert 'numpy' not in sys.modules; "
                "assert 'cv2' not in sys.modules; "
                "assert 'av' not in sys.modules"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
