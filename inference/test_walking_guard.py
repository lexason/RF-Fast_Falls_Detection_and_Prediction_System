#!/usr/bin/env python3
"""Validation harness for the walking-footstep-noise guard (STATE.md
2026-08-02): replays a recorded session through the SAME orchestration logic
as realtime_classifier.py's main() loop (not just LiveEventDetector in
isolation), since the fix lives in how the continuous-path context combines
with transient classification, not in the detector itself.

Usage:
    python inference/test_walking_guard.py --session-id 2026-08-02_live_test_block1
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "inference"))
from label_tool import compute_energy_trace  # noqa: E402
from realtime_classifier import EventWindowQueue, LiveEventDetector, ProductionModel, window_features, WINDOW_S, HOP_S  # noqa: E402


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
    frame_buf = deque()
    BUFFER_S = 8.0
    last_continuous_eval = 0.0
    last_continuous_label = "idle"

    published, suppressed = [], []

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
            wf = [(ft, fm) for ft, fm in frame_buf if w0 <= ft < w1]
            if len(wf) >= 5:
                ftimes = np.array([f[0] for f in wf])
                fmags = np.stack([f[1] for f in wf])
                feats = window_features(fmags, freqs, f0_hz, frame_times=ftimes, event_t0=t0, event_t1=t1)
                label, score = model.classify_transient(feats)
                if last_continuous_label == "walk" and label == "stand_up":
                    suppressed.append((t0, t1, label, score))
                else:
                    published.append((t0, t1, label, score))

        if detector.state == "quiet" and t - last_continuous_eval >= HOP_S:
            last_continuous_eval = t
            w0, w1 = t - WINDOW_S, t
            wf = [(ft, fm) for ft, fm in frame_buf if w0 <= ft < w1]
            if len(wf) >= 5:
                ftimes = np.array([f[0] for f in wf])
                fmags = np.stack([f[1] for f in wf])
                feats = window_features(fmags, freqs, f0_hz, frame_times=ftimes, event_t0=None, event_t1=None)
                label, score = model.classify_continuous(feats)
                if label != "transient":
                    last_continuous_label = label

    from collections import Counter
    print(f"{args.session_id}: {len(published)} published, {len(suppressed)} suppressed "
          f"(would-be total {len(published)+len(suppressed)})")
    print("published label counts:", dict(Counter(l for _, _, l, _ in published)))
    print("suppressed label counts:", dict(Counter(l for _, _, l, _ in suppressed)))


if __name__ == "__main__":
    main()
