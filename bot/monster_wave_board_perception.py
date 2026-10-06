"""A1-only exact-pixel memoization; each output belongs to its fresh frame."""
import numpy as np
import cv2

from bot.geometry import relative_region_to_pixels
from bot.observations import ObservationBatch
from bot.perception.local_cv import LocalCvDetector


class MonsterWaveBoardPerception:
    def __init__(self, perception):
        self.detectors = perception.detectors
        self._last = {}

    def analyze(self, snapshot):
        image = snapshot.image
        height, width = image.shape[:2]
        observations = []
        self.last_cached_count = 0
        for index, detector in enumerate(self.detectors):
            # Only this pure detector reads exactly its declared region.
            # Specialized detectors always run, preserving all resolver inputs.
            if type(detector) is LocalCvDetector:
                x1, y1, x2, y2 = relative_region_to_pixels(detector.spec.region, width, height)
                crop = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                previous = self._last.get(index)
                if previous is not None and previous[0] == image.shape and np.array_equal(previous[1], crop):
                    emitted = previous[2]
                    self.last_cached_count += 1
                else:
                    emitted = tuple(detector.detect(image))
                    self._last[index] = (image.shape, crop.copy(), emitted)
            else:
                emitted = tuple(detector.detect(image))
            observations.extend(emitted)
        return ObservationBatch(snapshot.sequence, snapshot.timestamp, tuple(observations))
