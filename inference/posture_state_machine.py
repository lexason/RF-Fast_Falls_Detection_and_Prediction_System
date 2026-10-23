#!/usr/bin/env python3
"""Research state aggregator with explicit unknown and stale-source states.

Single-channel Doppler cannot observe a stationary person's posture or infer
that a person is absent.  The state machine therefore preserves uncertainty
instead of inventing standing/absence states, and calls fall outputs
``fall_candidate`` rather than alerts.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque

import zmq

EVENT_TO_STATE = {
    "sit_down": "sitting_inferred",
    "stand_up": "standing_inferred",
    "lie_down": "lying_inferred",
    "fall": "fall_candidate",
}
SOURCE_STALE_TIMEOUT_S = 5.0
TIMELINE_MAXLEN = 5000


class PostureStateMachine:
    def __init__(self, now: float | None = None):
        started = time.time() if now is None else now
        self.state = "unknown"
        self.research_score: float | None = None
        self.last_transition_t = started
        self.last_message_wall_time = started
        self.timeline: deque[dict[str, object]] = deque(maxlen=TIMELINE_MAXLEN)

    @staticmethod
    def _valid_score(score: object) -> float:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            raise ValueError("research_score must be a finite number")
        return float(score)

    def handle_transient(
        self,
        label: str,
        research_score: float,
        timestamp: float,
        context: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        score = self._valid_score(research_score)
        new_state = EVENT_TO_STATE.get(label)
        if new_state is None:
            return None
        changed = new_state != self.state
        self.state = new_state
        self.research_score = score
        self.last_transition_t = timestamp
        record = {"t": timestamp, "event": label, "state": new_state, "research_score": score}
        self.timeline.append(record)
        event_type = "fall_candidate" if label == "fall" else "state_change"
        return {
            "type": event_type,
            "timestamp": timestamp,
            "event": label,
            "state": self.state,
            "research_score": score,
            "changed": changed,
            **(context or {}),
        }

    def handle_continuous(
        self,
        label: str,
        research_score: float,
        timestamp: float,
        context: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        score = self._valid_score(research_score)
        if label == "walk":
            new_state = "walking_observed"
        elif label == "idle" and self.state == "walking_observed":
            new_state = "static_posture_unknown"
        else:
            return None
        changed = new_state != self.state
        self.state = new_state
        self.research_score = score
        if not changed:
            return None
        self.timeline.append({"t": timestamp, "event": label, "state": new_state, "research_score": score})
        return {
            "type": "state_change",
            "timestamp": timestamp,
            "event": label,
            "state": self.state,
            "research_score": score,
            "changed": True,
            **(context or {}),
        }

    def check_stale(self, wall_time: float) -> dict[str, object] | None:
        if self.state != "sensor_unavailable" and wall_time - self.last_message_wall_time > SOURCE_STALE_TIMEOUT_S:
            self.state = "sensor_unavailable"
            self.research_score = None
            self.timeline.append(
                {"t": wall_time, "event": "source_stale", "state": self.state, "research_score": None}
            )
            return {
                "type": "quality_change",
                "timestamp": wall_time,
                "event": "source_stale",
                "state": self.state,
                "research_score": None,
                "quality_status": "sensor_unavailable",
                "changed": True,
            }
        return None

    # Kept as an explicit compatibility alias; it no longer infers absence.
    def check_absent(self, timestamp: float) -> dict[str, object] | None:
        return self.check_stale(timestamp)

    def handle_message(self, event: dict[str, object], wall_time: float | None = None) -> dict[str, object] | None:
        observed_wall_time = time.time() if wall_time is None else wall_time
        if not isinstance(observed_wall_time, (int, float)) or not math.isfinite(float(observed_wall_time)):
            raise ValueError("wall_time must be finite")
        event_type = event.get("type")
        if event_type not in {"heartbeat", "transient_event", "state_update"}:
            raise ValueError(f"unsupported event type: {event_type!r}")
        timestamp = event.get("timestamp")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(float(timestamp)):
            raise ValueError("event timestamp contract is invalid")
        if event_type == "heartbeat":
            self.last_message_wall_time = float(observed_wall_time)
            recovered = self.state == "sensor_unavailable"
            if self.state == "sensor_unavailable":
                self.state = "unknown"
            return {
                "type": "heartbeat",
                "timestamp": float(timestamp),
                "event": "source_heartbeat",
                "state": self.state,
                "research_score": self.research_score,
                "quality_status": event.get("quality_status", "usable"),
                "model_id": event.get("model_id"),
                "model_performance_gate_passed": event.get("model_performance_gate_passed"),
                "score_kind": event.get("score_kind"),
                "operating_mode": event.get("operating_mode"),
                "changed": recovered,
            }
        label = event.get("label")
        score = event.get("research_score")
        if not isinstance(label, str):
            raise ValueError("event label contract is invalid")
        validated_score = self._valid_score(score)
        self.last_message_wall_time = float(observed_wall_time)
        if self.state == "sensor_unavailable":
            self.state = "unknown"
        context = {
            key: event[key]
            for key in (
                "schema_version",
                "model_id",
                "model_performance_gate_passed",
                "score_kind",
                "quality_status",
                "operating_mode",
                "source_event_t0",
                "source_event_t1",
                "classification_window_t0",
                "classification_window_t1",
                "classification_delay_s",
                "event_duration_s",
            )
            if key in event
        }
        if event_type == "transient_event":
            return self.handle_transient(label, validated_score, float(timestamp), context)
        if event_type == "state_update":
            return self.handle_continuous(label, validated_score, float(timestamp), context)
        raise AssertionError("event type was validated above")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-addr", default="tcp://127.0.0.1:5593")
    parser.add_argument("--out-addr", default="tcp://127.0.0.1:5594")
    args = parser.parse_args()

    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b"")
    subscriber.setsockopt(zmq.RCVTIMEO, 1000)
    subscriber.setsockopt(zmq.LINGER, 0)
    subscriber.connect(args.in_addr)
    publisher = context.socket(zmq.PUB)
    publisher.setsockopt(zmq.LINGER, 0)
    publisher.bind(args.out_addr)

    machine = PostureStateMachine()
    print(f"research state aggregator: {args.in_addr} -> {args.out_addr}; initial=unknown", file=sys.stderr)
    try:
        while True:
            try:
                message = subscriber.recv_string()
            except zmq.Again:
                stale = machine.check_stale(time.time())
                if stale:
                    publisher.send_string(json.dumps(stale, allow_nan=False))
                continue
            try:
                event = json.loads(message)
                output = machine.handle_message(event)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                print(f"discarded invalid classifier event: {exc}", file=sys.stderr)
                continue
            if output is not None:
                publisher.send_string(json.dumps(output, allow_nan=False))
                if output["type"] == "fall_candidate":
                    print(
                        f"[PROBABLE FALL CANDIDATE] t={output['timestamp']:.2f} "
                        f"score={output['research_score']:.3f}",
                        file=sys.stderr,
                    )
                elif output.get("changed"):
                    print(f"state -> {output['state']} (via {output['event']})", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        subscriber.close(0)
        publisher.close(0)
        context.term()


if __name__ == "__main__":
    main()
