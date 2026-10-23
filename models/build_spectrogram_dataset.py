#!/usr/bin/env python3
"""G3 classifier v2: build a windowed spectrogram-patch dataset for the CNN.

Reuses the exact same window boundaries as v1 (models/build_dataset.py's
timeline construction, idle-fill/exclusion logic, and per-event/per-span
windowing) so the two classifiers are compared on identical data -- only the
per-window representation differs: v1 collapses each window to 6-8 scalar
features, v2 keeps the raw [freq_bins, time_frames] spectrogram patch for a
CNN to learn its own representation from (CLAUDE.md §6 G3 task 3).

Patch shape is fixed at (154, 60) -- 154 Doppler bins (the +/-300Hz crop at
this sample rate/window), 60 time frames (3s window / 50ms hop). See
docs/errata.md for why this is (Doppler bins x time frames) rather than the
framework doc's (Doppler bins x range bins) -- this project has no range axis.

Usage:
    python models/build_spectrogram_dataset.py
"""
import sys
from pathlib import Path

import json
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "models"))
from label_tool import compute_energy_trace  # noqa: E402
from build_dataset import (  # noqa: E402
    SESSION_IDS, UNVERIFIED_LABELS, build_timeline, session_day,
    windows_for_continuous_span, window_for_event,
    CONTINUOUS_LABELS, TRANSIENT_LABELS,
)

N_FRAMES_TARGET = 60  # 3s window / 50ms hop


def fit_patch(frames):
    """Pad/crop a [n_frames, n_bins] window to exactly [N_FRAMES_TARGET, n_bins]."""
    n = frames.shape[0]
    if n == N_FRAMES_TARGET:
        return frames
    if n > N_FRAMES_TARGET:
        start = (n - N_FRAMES_TARGET) // 2
        return frames[start:start + N_FRAMES_TARGET]
    pad = N_FRAMES_TARGET - n
    pad_before = pad // 2
    pad_after = pad - pad_before
    return np.pad(frames, ((pad_before, pad_after), (0, 0)), mode="edge")


def process_session(session_id):
    session_dir = REPO_ROOT / "data" / "raw" / session_id
    manifest = json.loads((session_dir / "manifest.json").read_text())
    fs = manifest["sample_rate_hz"]
    iq = np.fromfile(session_dir / f"{session_id}.sigmf-data", dtype=np.complex64)
    duration_s = len(iq) / fs

    times, energy, frames, lo, hi, nperseg = compute_energy_trace(iq, fs)
    timeline = build_timeline(session_id, duration_s)
    day = session_day(session_id)

    window_specs = []
    for t0, t1, label in timeline:
        if label in CONTINUOUS_LABELS:
            window_specs.extend(windows_for_continuous_span(t0, t1, label))
        elif label in TRANSIENT_LABELS:
            window_specs.extend(window_for_event(t0, t1, label, duration_s))

    patches, meta = [], []
    for w0, w1, label, event_bounds in window_specs:
        mask = (times >= w0) & (times < w1)
        if mask.sum() >= 5:
            patch = fit_patch(frames[mask])  # [N_FRAMES_TARGET, n_bins]
            confidence = "unverified" if (session_id, label) in UNVERIFIED_LABELS else "verified"
            patches.append(patch)
            meta.append({
                "session_id": session_id, "day": day, "t_start": w0, "t_end": w1,
                "label": label, "label_confidence": confidence,
            })
    return patches, meta


def main():
    all_patches, all_meta = [], []
    for session_id in SESSION_IDS:
        patches, meta = process_session(session_id)
        print(f"{session_id}: {len(patches)} patches")
        all_patches.extend(patches)
        all_meta.extend(meta)

    X = np.stack(all_patches).astype(np.float32)  # [N, 60, 154]
    meta_df = pd.DataFrame(all_meta)

    out_dir = REPO_ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "g3_spectrogram_patches.npy", X)
    meta_df.to_parquet(out_dir / "g3_spectrogram_meta.parquet", index=False)

    print(f"\nwrote {out_dir / 'g3_spectrogram_patches.npy'}: shape {X.shape}")
    print(f"wrote {out_dir / 'g3_spectrogram_meta.parquet'}: {len(meta_df)} rows")
    print("\nlabel counts:")
    print(meta_df["label"].value_counts())


if __name__ == "__main__":
    main()
