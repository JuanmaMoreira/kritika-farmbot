"""Visual evidence of the acquired central cyan loading animation.

No absence, action-effect, readiness or retry semantics. Deliberately excluded
from default perception: callers must opt in for a specific passive wait.
Thresholds frozen from the exploratory 2026-10-15 phase 2A slice.
Independent negatives produced false positives: no universal validation.
Runtime adoption is restricted to the receipt-bound MW Yes owner; see
docs/MONSTER_WAVE_SKIP.md. Algorithm and thresholds remain unchanged.
"""
import cv2
import numpy as np

from bot.geometry import frame_dimensions, relative_region_to_pixels
from bot.observations import Observation, ObservationSource

ACTIVITY_GLOBAL_LOADING = 'activity.global_loading'
LOADING_REGION = (.44, .40, .56, .60)
COLOR_REGION = (.47, .43, .53, .58)


def _crop_scaled(frame, region):
    width, height = frame_dimensions(frame)
    x1, y1, x2, y2 = relative_region_to_pixels(region, width, height)
    roi = frame[y1:y2, x1:x2]
    if not roi.size:
        return None
    # Radius thresholds are in an analysis scale, never device coordinates.
    return cv2.resize(roi, (max(1, round(roi.shape[1]*600/height)),
                            max(1, round(roi.shape[0]*600/height))),
                      interpolation=cv2.INTER_AREA)


def _cyan(roi):
    return cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV),
                       np.array([75, 100, 80], np.uint8),
                       np.array([105, 255, 255], np.uint8)) > 0


class GlobalLoadingDetector:
    evaluation_id = ACTIVITY_GLOBAL_LOADING

    def detect(self, frame):
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3 or not frame.size):
            raise ValueError('frame must be a nonempty uint8 BGR image')
        color = _crop_scaled(frame, COLOR_REGION)
        if color is None or float(np.mean(_cyan(color))) < .028:
            return ()
        roi = _crop_scaled(frame, LOADING_REGION)
        if roi is None:
            return ()
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        circles = cv2.HoughCircles(
            cv2.GaussianBlur(gray, (3, 3), 0), cv2.HOUGH_GRADIENT,
            dp=1, minDist=20, param1=90, param2=22, minRadius=18, maxRadius=38)
        if circles is None:
            return ()
        cyan = _cyan(roi)
        yy, xx = np.indices(gray.shape)
        for x, y, radius in circles[0]:
            distance = np.hypot(xx-x, yy-y)/radius
            core = distance < .32
            arc = (distance > .68) & (distance < 1.12)
            if (core.any() and arc.any() and float(np.mean(cyan[core])) >= .15
                    and float(np.mean(cyan[arc])) >= .03):
                # Fixed evidence grade, not a calibrated probability.
                return (Observation(ACTIVITY_GLOBAL_LOADING, .90,
                                    ObservationSource.LOCAL_CV, region=LOADING_REGION),)
        return ()
