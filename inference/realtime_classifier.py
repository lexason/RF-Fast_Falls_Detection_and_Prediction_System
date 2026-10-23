#!/usr/bin/env python3
"""Offline-capable DEVELOPMENT activity and fall-candidate classifier.

The service consumes spectrogram frames, waits until the complete three-second
event-centred window used during training is available, and publishes derived
research events.  It never emits a clinical alert and never labels its model
scores as calibrated confidence.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zmq

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "features"))
from dsp.spectrogram_service import doppler_frequencies  # noqa: E402
from inference.model_runtime import ModelContractError, ProductionModel  # noqa: E402
from micro_doppler import window_features  # noqa: E402

WINDOW_S = 3.0
HOP_S = 0.5
HIGH_DB, LOW_DB, MIN_EVENT_S = 30.0, 25.0, 0.15
MERGE_GAP_S = 0.6
BUFFER_S = 10.0
MIN_WINDOW_FRAMES = 5
MAX_FRAME_GAP_S = 0.15
WINDOW_EDGE_TOLERANCE_S = 0.15


class FrameContractError(ValueError):
    """A spectrogram message violates the internal wire contract."""


def decode_spectrogram_frame(message: bytes, expected_bins: int | None = None) -> tuple[float, np.ndarray]:
    if len(message) < 12 or (len(message) - 8) % 4:
        raise FrameContractError("frame must contain one float64 timestamp and float32 bins")
    timestamp = float(np.frombuffer(message[:8], dtype=np.float64, count=1)[0])
    magnitude = np.frombuffer(message[8:], dtype=np.float32).copy()
    if not math.isfinite(timestamp) or not np.all(np.isfinite(magnitude)):
        raise FrameContractError("frame contains NaN or infinity")
    if expected_bins is not None and len(magnitude) != expected_bins:
        raise FrameContractError(f"frame bin count changed from {expected_bins} to {len(magnitude)}")
    return timestamp, magnitude


class LiveEventDetector:
    """Causal hysteresis detector with the training pipeline's merge delay."""

    def __init__(
        self,
        high_db: float = HIGH_DB,
        low_db: float = LOW_DB,
        min_event_s: float = MIN_EVENT_S,
        merge_gap_s: float = MERGE_GAP_S,
    ):
        if not high_db > low_db:
            raise ValueError("high_db must be greater than low_db")
        if min_event_s <= 0 or merge_gap_s < 0:
            raise ValueError("event durations must be non-negative")
        self.high_db = high_db
        self.low_db = low_db
        self.min_event_s = min_event_s
        self.merge_gap_s = merge_gap_s
        self.state = "quiet"
        self.event_start: float | None = None
        self.provisional_end: float | None = None
        self.cooldown_start: float | None = None

    def process(self, timestamp: float, energy: float) -> tuple[float, float] | None:
        if not math.isfinite(timestamp) or not math.isfinite(energy):
            raise ValueError("detector inputs must be finite")
        if self.state == "quiet":
            if energy >= self.high_db:
                self.state = "active"
                self.event_start = timestamp
            return None
        if self.state == "active":
            if energy < self.low_db:
                self.state = "cooldown"
                self.provisional_end = timestamp
                self.cooldown_start = timestamp
            return None
        if energy >= self.high_db:
            self.state = "active"
            self.provisional_end = None
            self.cooldown_start = None
            return None
        assert self.cooldown_start is not None and self.event_start is not None
        if timestamp - self.cooldown_start >= self.merge_gap_s:
            event = (self.event_start, float(self.provisional_end))
            self.state = "quiet"
            self.event_start = self.provisional_end = self.cooldown_start = None
            if event[1] - event[0] >= self.min_event_s:
                return event
        return None


@dataclass(frozen=True)
class PendingEvent:
    event_t0: float
    event_t1: float
    window_t0: float
    window_t1: float


def event_window(event_t0: float, event_t1: float) -> PendingEvent:
    center = (event_t0 + event_t1) / 2.0
    return PendingEvent(event_t0, event_t1, center - WINDOW_S / 2.0, center + WINDOW_S / 2.0)


class EventWindowQueue:
    """Hold completed events until every post-event training frame exists."""

    def __init__(self):
        self.pending: deque[PendingEvent] = deque()

    def add(self, event_t0: float, event_t1: float) -> PendingEvent:
        pending = event_window(event_t0, event_t1)
        self.pending.append(pending)
        return pending

    def ready(self, current_timestamp: float) -> list[PendingEvent]:
        ready: list[PendingEvent] = []
        while self.pending and current_timestamp >= self.pending[0].window_t1:
            ready.append(self.pending.popleft())
        return ready


def _features_for_window(
    frames: deque[tuple[float, np.ndarray]],
    frequencies: np.ndarray,
    f0_hz: float,
    window_t0: float,
    window_t1: float,
    event_t0: float | None,
    event_t1: float | None,
) -> dict[str, float] | None:
    selected = [(timestamp, magnitude) for timestamp, magnitude in frames if window_t0 <= timestamp < window_t1]
    if len(selected) < MIN_WINDOW_FRAMES:
        return None
    times = np.asarray([item[0] for item in selected])
    if (
        times[0] - window_t0 > WINDOW_EDGE_TOLERANCE_S
        or window_t1 - times[-1] > WINDOW_EDGE_TOLERANCE_S
        or (len(times) > 1 and float(np.max(np.diff(times))) > MAX_FRAME_GAP_S)
    ):
        return None
    magnitudes = np.stack([item[1] for item in selected])
    result = window_features(
        magnitudes,
        frequencies,
        f0_hz,
        frame_times=times,
        event_t0=event_t0,
        event_t1=event_t1,
    )
    if not all(math.isfinite(float(value)) for value in result.values()):
        raise FrameContractError("feature extraction produced NaN or infinity")
    return result


def _base_event(model: ProductionModel, quality_status: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "model_id": model.model_id,
        "model_performance_gate_passed": model.quality_gate_passed,
        "score_kind": model.score_kind,
        "quality_status": quality_status,
        "operating_mode": "silent_research_poc",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-addr", default="tcp://127.0.0.1:5591")
    parser.add_argument("--out-addr", default="tcp://127.0.0.1:5593")
    parser.add_argument("--model-dir", default=str(REPO_ROOT / "models" / "production"))
    parser.add_argument("--samp-rate", type=float, default=250000.0)
    parser.add_argument(
        "--f0-hz",
        type=float,
        default=None,
        help="Radar carrier frequency (Hz), for Doppler-to-velocity feature conversion. "
             "Defaults to config/system.yaml's carrier.f0_hz -- override only for offline "
             "replay of a session captured at a different carrier.",
    )
    args = parser.parse_args()

    if args.f0_hz is not None:
        f0_hz = args.f0_hz
    else:
        import yaml
        f0_hz = yaml.safe_load((REPO_ROOT / "config" / "system.yaml").read_text())["carrier"]["f0_hz"]

    try:
        model = ProductionModel(args.model_dir)
    except ModelContractError as exc:
        raise SystemExit(f"model contract rejected: {exc}") from exc

    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b"")
    subscriber.setsockopt(zmq.RCVTIMEO, 1000)
    subscriber.setsockopt(zmq.LINGER, 0)
    subscriber.connect(args.in_addr)
    publisher = context.socket(zmq.PUB)
    publisher.setsockopt(zmq.LINGER, 0)
    publisher.bind(args.out_addr)

    detector = LiveEventDetector()
    pending = EventWindowQueue()
    frame_buffer: deque[tuple[float, np.ndarray]] = deque()
    try:
        frequencies = doppler_frequencies(args.samp_rate)
    except ValueError as exc:
        raise SystemExit(f"invalid DSP geometry: {exc}") from exc
    expected_bins = len(frequencies)
    previous_timestamp: float | None = None
    last_continuous_eval = float("-inf")
    last_heartbeat = float("-inf")
    last_continuous_label = "unknown"
    invalid_frames = 0

    print(
        f"research classifier: {args.in_addr} -> {args.out_addr}; model={model.model_id}; "
        f"sample_rate={args.samp_rate:g}; bins={expected_bins}; f0_hz={f0_hz:g}; "
        f"performance_gate=FAIL; output=silent candidates",
        file=sys.stderr,
    )

    try:
        while True:
            try:
                message = subscriber.recv()
            except zmq.Again:
                continue
            try:
                timestamp, magnitude = decode_spectrogram_frame(message, expected_bins)
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    raise FrameContractError("frame timestamps must be strictly increasing")
            except FrameContractError as exc:
                invalid_frames += 1
                print(f"discarded invalid spectrogram frame #{invalid_frames}: {exc}", file=sys.stderr)
                continue

            quality_status = "usable"
            if previous_timestamp is not None and timestamp - previous_timestamp > 0.25:
                quality_status = "degraded_timing_gap"
            previous_timestamp = timestamp
            frame_buffer.append((timestamp, magnitude))
            while frame_buffer and timestamp - frame_buffer[0][0] > BUFFER_S:
                frame_buffer.popleft()

            if timestamp - last_heartbeat >= 1.0:
                last_heartbeat = timestamp
                publisher.send_string(
                    json.dumps(
                        {
                            **_base_event(model, quality_status),
                            "type": "heartbeat",
                            "timestamp": timestamp,
                        },
                        allow_nan=False,
                    )
                )

            completed = detector.process(timestamp, float(np.max(magnitude)))
            if completed is not None:
                pending.add(*completed)

            for event in pending.ready(timestamp):
                features = _features_for_window(
                    frame_buffer,
                    frequencies,
                    f0_hz,
                    event.window_t0,
                    event.window_t1,
                    event.event_t0,
                    event.event_t1,
                )
                if features is None:
                    print("abstained: incomplete event window", file=sys.stderr)
                    continue
                label, score = model.classify_transient(features)
                if last_continuous_label == "walk" and label == "stand_up":
                    print("suppressed research transition candidate during walking context", file=sys.stderr)
                    continue
                payload = {
                    **_base_event(model, quality_status),
                    "type": "transient_event",
                    "timestamp": timestamp,
                    "source_event_t0": event.event_t0,
                    "source_event_t1": event.event_t1,
                    "classification_window_t0": event.window_t0,
                    "classification_window_t1": event.window_t1,
                    "classification_delay_s": timestamp - event.event_t1,
                    "label": label,
                    "research_score": score,
                    "event_duration_s": event.event_t1 - event.event_t0,
                }
                publisher.send_string(json.dumps(payload, allow_nan=False))
                if label == "fall":
                    print(f"[PROBABLE FALL CANDIDATE] t={timestamp:.2f} score={score:.4f}", file=sys.stderr)

            if detector.state == "quiet" and timestamp - last_continuous_eval >= HOP_S:
                last_continuous_eval = timestamp
                features = _features_for_window(
                    frame_buffer,
                    frequencies,
                    f0_hz,
                    timestamp - WINDOW_S,
                    timestamp,
                    None,
                    None,
                )
                if features is None:
                    continue
                label, score = model.classify_continuous(features)
                if label != "transient":
                    last_continuous_label = label
                    publisher.send_string(
                        json.dumps(
                            {
                                **_base_event(model, quality_status),
                                "type": "state_update",
                                "timestamp": timestamp,
                                "label": label,
                                "research_score": score,
                            },
                            allow_nan=False,
                        )
                    )
    except KeyboardInterrupt:
        pass
    finally:
        subscriber.close(0)
        publisher.close(0)
        context.term()


if __name__ == "__main__":
    main()
