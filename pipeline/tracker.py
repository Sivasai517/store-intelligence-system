"""
tracker.py - ByteTrack-based multi-object tracker for the Store Intelligence System.

Assigns persistent track IDs to detected persons across video frames.
Uses a simplified ByteTrack implementation for production tracking.

Usage:
    from pipeline.tracker import ByteTracker
    tracker = ByteTracker()
    tracks = tracker.update(detections, frame_shape)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from pipeline.detect import Detection

logger = logging.getLogger("store_intelligence.pipeline")


@dataclass
class Track:
    """A tracked person across frames."""
    track_id: int
    bbox: list[float]           # [x1, y1, x2, y2]
    confidence: float
    age: int = 0                # Number of frames since creation
    hits: int = 1               # Total frames where this track was matched
    time_since_update: int = 0  # Frames since last matched detection
    center_history: list[tuple[float, float]] = field(default_factory=list)

    @property
    def center(self) -> tuple[float, float]:
        """Current center of the bounding box."""
        cx = (self.bbox[0] + self.bbox[2]) / 2
        cy = (self.bbox[1] + self.bbox[3]) / 2
        return (cx, cy)

    @property
    def is_confirmed(self) -> bool:
        """Track is confirmed after N hits."""
        return self.hits >= 3


def _iou(bbox1: list[float], bbox2: list[float]) -> float:
    """Compute IoU between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def _compute_iou_matrix(
    tracks: list[Track], detections: list[Detection]
) -> np.ndarray:
    """Compute IoU cost matrix between existing tracks and new detections."""
    if not tracks or not detections:
        return np.zeros((len(tracks), len(detections)))

    matrix = np.zeros((len(tracks), len(detections)))
    for i, track in enumerate(tracks):
        for j, det in enumerate(detections):
            matrix[i, j] = _iou(track.bbox, det.bbox)
    return matrix


class ByteTracker:
    """
    Simplified ByteTrack multi-object tracker.

    ByteTrack key ideas:
    1. Associate high-confidence detections first (first association)
    2. Then match remaining tracks with low-confidence detections (second association)
    3. This recovers tracks that might be lost due to occlusion or motion blur

    This implementation uses greedy matching with IoU for simplicity while
    maintaining the core ByteTrack concept.
    """

    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
        high_conf_threshold: float = 0.5,
    ):
        """
        Initialise the ByteTracker.

        Args:
            max_age: Maximum frames to keep a track without updates.
            min_hits: Minimum hits before a track is confirmed.
            iou_threshold: IoU threshold for matching.
            high_conf_threshold: Confidence split for ByteTrack's two-stage matching.
        """
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.high_conf_threshold = high_conf_threshold

        self._tracks: list[Track] = []
        self._next_id: int = 1
        self._frame_count: int = 0

    def update(self, detections: list[Detection]) -> list[Track]:
        """
        Update tracker state with new detections.

        Implements ByteTrack's two-stage association:
        1. Match high-confidence detections with existing tracks
        2. Match unmatched tracks with low-confidence detections

        Args:
            detections: List of Detection objects from the current frame.

        Returns:
            List of active (confirmed) Track objects.
        """
        self._frame_count += 1

        # Split detections into high and low confidence
        high_dets = [d for d in detections if d.confidence >= self.high_conf_threshold]
        low_dets = [d for d in detections if d.confidence < self.high_conf_threshold]

        # --- First Association: Match tracks with high-confidence detections ---
        matched_track_indices: set[int] = set()
        matched_det_indices: set[int] = set()

        if self._tracks and high_dets:
            iou_matrix = _compute_iou_matrix(self._tracks, high_dets)

            # Greedy matching (highest IoU first)
            while True:
                if iou_matrix.size == 0:
                    break
                max_iou = iou_matrix.max()
                if max_iou < self.iou_threshold:
                    break

                max_idx = np.unravel_index(iou_matrix.argmax(), iou_matrix.shape)
                t_idx, d_idx = int(max_idx[0]), int(max_idx[1])

                if t_idx not in matched_track_indices and d_idx not in matched_det_indices:
                    # Update matched track
                    track = self._tracks[t_idx]
                    det = high_dets[d_idx]
                    track.bbox = det.bbox
                    track.confidence = det.confidence
                    track.hits += 1
                    track.time_since_update = 0
                    track.center_history.append(track.center)
                    if len(track.center_history) > 100:
                        track.center_history = track.center_history[-100:]

                    matched_track_indices.add(t_idx)
                    matched_det_indices.add(d_idx)

                # Zero out the matched row/col to prevent re-matching
                iou_matrix[t_idx, :] = 0
                iou_matrix[:, d_idx] = 0

        # --- Second Association: Match unmatched tracks with low-confidence detections ---
        unmatched_track_indices = [
            i for i in range(len(self._tracks)) if i not in matched_track_indices
        ]

        if unmatched_track_indices and low_dets:
            unmatched_tracks = [self._tracks[i] for i in unmatched_track_indices]
            iou_matrix_low = _compute_iou_matrix(unmatched_tracks, low_dets)

            matched_low_tracks: set[int] = set()
            matched_low_dets: set[int] = set()

            while True:
                if iou_matrix_low.size == 0:
                    break
                max_iou = iou_matrix_low.max()
                if max_iou < self.iou_threshold:
                    break

                max_idx = np.unravel_index(
                    iou_matrix_low.argmax(), iou_matrix_low.shape
                )
                ut_idx, ld_idx = int(max_idx[0]), int(max_idx[1])

                if ut_idx not in matched_low_tracks and ld_idx not in matched_low_dets:
                    original_idx = unmatched_track_indices[ut_idx]
                    track = self._tracks[original_idx]
                    det = low_dets[ld_idx]
                    track.bbox = det.bbox
                    track.confidence = det.confidence
                    track.hits += 1
                    track.time_since_update = 0
                    track.center_history.append(track.center)
                    if len(track.center_history) > 100:
                        track.center_history = track.center_history[-100:]

                    matched_track_indices.add(original_idx)
                    matched_low_tracks.add(ut_idx)
                    matched_low_dets.add(ld_idx)

                iou_matrix_low[ut_idx, :] = 0
                iou_matrix_low[:, ld_idx] = 0

        # --- Create new tracks for unmatched high-confidence detections ---
        for j, det in enumerate(high_dets):
            if j not in matched_det_indices:
                new_track = Track(
                    track_id=self._next_id,
                    bbox=det.bbox,
                    confidence=det.confidence,
                )
                new_track.center_history.append(new_track.center)
                self._tracks.append(new_track)
                self._next_id += 1

        # --- Age management ---
        for i, track in enumerate(self._tracks):
            track.age += 1
            if i not in matched_track_indices:
                track.time_since_update += 1

        # --- Remove dead tracks ---
        self._tracks = [
            t for t in self._tracks if t.time_since_update <= self.max_age
        ]

        # --- Return confirmed tracks ---
        return [t for t in self._tracks if t.is_confirmed]

    def reset(self) -> None:
        """Reset the tracker state."""
        self._tracks.clear()
        self._next_id = 1
        self._frame_count = 0

    @property
    def active_track_count(self) -> int:
        """Number of currently active confirmed tracks."""
        return len([t for t in self._tracks if t.is_confirmed])
