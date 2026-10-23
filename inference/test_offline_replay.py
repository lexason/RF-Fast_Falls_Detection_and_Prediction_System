#!/usr/bin/env python3
"""Offline validation of the real-time classifier's transient-detection path
(LiveEventDetector + ProductionModel.classify_transient), by replaying a
recorded session's clutter-removed frames through the exact same code the
live service uses -- a stand-in for physical live testing when nobody's in
the lab, exercising the identical inference path end-to-end.

Usage:
    python inference/test_offline_replay.py --session-id 2026-07-29_floor_fall_reps_b
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "inference"))
from label_tool import compute_energy_trace  # noqa: E402
from realtime_classifier import EventWindowQueue, LiveEventDetector, ProductionModel, window_features  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", required=True)
    args = ap.parse_args()

    session_dir = REPO_ROOT / "data" / "raw" / args.session_id
    manifest = json.loads((session_dir / "manifest.json").read_text())
    fs = manifest["sample_rate_hz"]
    f0_hz = manifest["carrier_hz"]
    iq = np.fromfile(session_dir / f"{args.session_id}.sigmf-data", dtype=np.complex64)
    times, energy, frames, lo, hi, nperseg = compute_energy_trace(iq, fs)
    freq_res = fs / nperseg
    n_bins = hi - lo
    freqs = (np.arange(n_bins) - n_bins / 2) * freq_res

    model = ProductionModel(REPO_ROOT / "models" / "production")
    detector = LiveEventDetector()
    pending = EventWindowQueue()

    from collections import deque
    frame_buf = deque()
    BUFFER_S = 8.0
    results = []

    for i in range(len(times)):
        t = times[i]
        frame_buf.append((t, frames[i]))
        while frame_buf and t - frame_buf[0][0] > BUFFER_S:
            frame_buf.popleft()

        e = float(np.max(frames[i]))
        completed = detector.process(t, e)
        if completed is not None:
            pending.add(*completed)
        for event in pending.ready(t):
            t0, t1 = event.event_t0, event.event_t1
            w0, w1 = event.window_t0, event.window_t1
            window_frames = [(ft, fm) for ft, fm in frame_buf if w0 <= ft < w1]
            if len(window_frames) >= 5:
                ftimes = np.array([f[0] for f in window_frames])
                fmags = np.stack([f[1] for f in window_frames])
                feats = window_features(fmags, freqs, f0_hz, frame_times=ftimes, event_t0=t0, event_t1=t1)
                label, score = model.classify_transient(feats)
                results.append((t0, t1, label, score))

    print(f"session: {args.session_id} ({manifest.get('activity_class', '?')})")
    print(f"{len(results)} transient events detected and classified:")
    for t0, t1, label, score in results:
        marker = " <-- PROBABLE FALL CANDIDATE" if label == "fall" else ""
        print(f"  {t0:7.2f}s-{t1:7.2f}s  {label:10s} research_score={score:.3f}{marker}")


if __name__ == "__main__":
    main()
