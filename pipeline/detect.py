"""
detect.py - YOLOv8-based person detection for the Store Intelligence System.

Uses the YOLOv8n (nano) pre-trained model to detect persons (COCO class 0)
in video frames. Designed to process CCTV footage frame-by-frame.

Usage:
    from pipeline.detect import PersonDetector
    detector = PersonDetector()
    detections = detector.detect(frame)  # returns list of Detection objects
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger("store_intelligence.pipeline")

# COCO class index for 'person'
PERSON_CLASS_ID = 0

# Minimum confidence threshold for person detections
DEFAULT_CONFIDENCE_THRESHOLD = 0.35


@dataclass
class Detection:
    """A single person detection in a frame."""
    bbox: list[float]       # [x1, y1, x2, y2] in pixel coordinates
    confidence: float       # Detection confidence score (0-1)
    class_id: int = 0       # Always 0 (person)

    @property
    def center(self) -> tuple[float, float]:
        """Return the center (x, y) of the bounding box."""
        cx = (self.bbox[0] + self.bbox[2]) / 2
        cy = (self.bbox[1] + self.bbox[3]) / 2
        return (cx, cy)

    @property
    def area(self) -> float:
        """Return the area of the bounding box."""
        w = self.bbox[2] - self.bbox[0]
        h = self.bbox[3] - self.bbox[1]
        return max(0.0, w * h)


class PersonDetector:
    """
    YOLOv8 person detector wrapper.

    Loads the YOLOv8n model and filters detections to only return
    persons (class 0) above the confidence threshold.
    """

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        device: Optional[str] = None,
    ):
        """
        Initialise the person detector.

        Args:
            model_path: Path to the YOLOv8 model weights.
            confidence_threshold: Minimum confidence to accept a detection.
            device: Inference device ('cpu', 'cuda', '0', etc.). Auto-selects if None.
        """
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "ultralytics package is required. Install with: pip install ultralytics"
            )

        self.confidence_threshold = confidence_threshold
        self.model = YOLO(model_path)
        self._device = device

        logger.info(
            "PersonDetector initialised",
            extra={
                "model_path": model_path,
                "confidence_threshold": confidence_threshold,
                "device": device or "auto",
            },
        )

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Run person detection on a single frame.

        Args:
            frame: BGR image as a NumPy array (H, W, 3).

        Returns:
            List of Detection objects for persons found in the frame.
        """
        results = self.model(
            frame,
            verbose=False,
            conf=self.confidence_threshold,
            classes=[PERSON_CLASS_ID],
            device=self._device,
        )

        detections: list[Detection] = []

        for result in results:
            if result.boxes is None:
                continue

            boxes = result.boxes
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].cpu().numpy().tolist()
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())

                # Double-check it's a person (should always be due to classes filter)
                if cls_id == PERSON_CLASS_ID and conf >= self.confidence_threshold:
                    detections.append(
                        Detection(
                            bbox=bbox,
                            confidence=conf,
                            class_id=cls_id,
                        )
                    )

        return detections

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[Detection]]:
        """
        Run detection on a batch of frames.

        Args:
            frames: List of BGR images as NumPy arrays.

        Returns:
            List of detection lists, one per input frame.
        """
        all_results = self.model(
            frames,
            verbose=False,
            conf=self.confidence_threshold,
            classes=[PERSON_CLASS_ID],
            device=self._device,
        )

        batch_detections: list[list[Detection]] = []

        for result in all_results:
            frame_detections: list[Detection] = []
            if result.boxes is not None:
                boxes = result.boxes
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy().tolist()
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())

                    if cls_id == PERSON_CLASS_ID and conf >= self.confidence_threshold:
                        frame_detections.append(
                            Detection(bbox=bbox, confidence=conf, class_id=cls_id)
                        )
            batch_detections.append(frame_detections)

        return batch_detections
