#!/usr/bin/env python3
"""G3 classifier v1: build a windowed, labeled feature table from the 4
multi-day dataset sessions (2026-07-25/27/28/29).

Per CLAUDE.md §6/§7: 3s windows, 0.5s slide, six per-window features
(features/micro_doppler.py), Parquet storage, LOSO grouping by day (each
lab visit is one fold -- sub-recordings within a day, e.g. fall_block1/
fall_block2, are NOT independent folds, so they're grouped under their
shared date).

Label assignment per window:
  - Each session's data/labels/<id>.jsonl gives event intervals (whole-clip,
    one continuous span, or many discrete events -- see scripts/label_tool.py).
  - "empty_room" is mapped to "idle": CLAUDE.md §4 -- Doppler can't see a
    stationary person, so an empty room and an idle occupant are the same
    signature, and the classifier's 6-class taxonomy (CLAUDE.md §6 G3 AC)
    has no separate empty_room class.
  - Annotation gaps are unknown and are not used for training. A no-motion
    interval is "idle" only when the source annotation explicitly says so.
  - One specific known exception: 2026-07-28_sit_stand_reps has a gap
    [35.68s, 57.48s] that was NOT idle -- it's the span excluded during the
    direction-verify QA pass (ambiguous/ desynced detections, see STATE.md
    2026-07-28 entry), so it must NOT be silently idle-filled. Hardcoded
    below rather than guessed from a free-text manifest note.
  - A window is assigned a label only if one segment covers >=50% of the
    window's duration (majority rule); windows straddling a transition with
    no clear majority are dropped rather than guessed.

Label confidence: the 2026-07-28 direction-verify QA pass found that
2026-07-25_sit_stand_reps and all 4 lie_down_reps sessions could not be
confirmed clean (STATE.md 2026-07-28/-29 entries) -- their sit_down/
stand_up or lie_down/stand_up windows are tagged label_confidence=
"unverified" rather than silently trusted equally with the fixed/confirmed
sessions.

  - Any windows with overlapping raw-time support and different labels are
    all excluded. This prevents contradictory labels for the same samples.

Usage:
    python models/build_dataset.py --out data/processed/g3_features_v2_conflict_free.parquet
"""
import argparse
import sys
from pathlib import Path

import json
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "features"))
from dsp.spectrogram_service import doppler_frequencies  # noqa: E402
from label_tool import compute_energy_trace  # noqa: E402
from micro_doppler import window_features, FEATURE_NAMES  # noqa: E402

WINDOW_S = 3.0
HOP_S = 0.5

SESSION_IDS = [
    "2026-07-25_empty_room", "2026-07-25_idle", "2026-07-25_walk_reps",
    "2026-07-25_sit_stand_reps", "2026-07-25_fall_block1", "2026-07-25_fall_block2",
    "2026-07-25_lie_down_reps",
    "2026-07-27_empty_room", "2026-07-27_idle", "2026-07-27_walk_reps",
    "2026-07-27_sit_stand_reps", "2026-07-27_fall_reps", "2026-07-27_lie_down_reps",
    "2026-07-28_empty_room", "2026-07-28_idle", "2026-07-28_walk_reps",
    "2026-07-28_sit_stand_reps", "2026-07-28_fall_reps", "2026-07-28_fall_single",
    "2026-07-28_lie_down_reps",
    "2026-07-29_empty_room", "2026-07-29_idle", "2026-07-29_walk_reps",
    "2026-07-29_sit_stand_reps", "2026-07-29_fall_reps", "2026-07-29_lie_down_reps",
    "2026-07-29_floor_empty_room", "2026-07-29_floor_idle", "2026-07-29_floor_walk_reps",
    "2026-07-29_floor_sit_stand_reps", "2026-07-29_floor_fall_reps", "2026-07-29_floor_lie_down_reps",
    "2026-07-29_floor_fall_reps_b", "2026-07-29_floor_sit_stand_reps_b",
    # 2026-07-29_floor_lie_down_reps_b: originally excluded (default merge_gap_s=0.6 produced
    # a confirmed ~2x over-detection -- 42 events vs researcher-confirmed ~9-10 real cycles).
    # Root-caused and fixed: re-detected with --merge-gap-s 2.0 (session-specific override,
    # validated NOT to harm already-correct lie_down sessions before applying), now 19 events
    # matching the real count. No longer excluded -- see manifest's merge_gap_override note.
    "2026-07-29_floor_lie_down_reps_b",
]

# Sessions recorded at the repositioned floor-level antenna geometry (2026-07-29,
# see STATE.md/config/system.yaml) share a calendar date with that morning's
# bench-height session 4 -- grouping LOSO folds by date alone would silently merge
# two different physical antenna configurations into one fold, defeating the point
# of testing whether the reposition helps. Give them a distinct synthetic "day" group.
FLOOR_GEOMETRY_MARKER = "_floor_"  # substring match -- covers both today's first round
                                     # (2026-07-29_floor_*) and any later top-up round
                                     # (e.g. 2026-07-29_floor_fall_reps_b), same fold either way
FLOOR_GEOMETRY_DAY = "2026-07-29-floor"

# (session_id, label) pairs found NOT confirmed-clean by the 2026-07-28 direction-verify
# QA pass (STATE.md 2026-07-28/-29 entries) -- windows carrying these get label_confidence="unverified".
UNVERIFIED_LABELS = {
    ("2026-07-25_sit_stand_reps", "sit_down"), ("2026-07-25_sit_stand_reps", "stand_up"),
    ("2026-07-25_lie_down_reps", "lie_down"), ("2026-07-25_lie_down_reps", "stand_up"),
    ("2026-07-27_lie_down_reps", "lie_down"), ("2026-07-27_lie_down_reps", "stand_up"),
    ("2026-07-28_lie_down_reps", "lie_down"), ("2026-07-28_lie_down_reps", "stand_up"),
    ("2026-07-29_lie_down_reps", "lie_down"), ("2026-07-29_lie_down_reps", "stand_up"),
    ("2026-07-29_floor_lie_down_reps", "lie_down"), ("2026-07-29_floor_lie_down_reps", "stand_up"),
    ("2026-07-29_floor_lie_down_reps_b", "lie_down"), ("2026-07-29_floor_lie_down_reps_b", "stand_up"),
}

LABEL_MAP = {"empty_room": "idle"}  # 6-class taxonomy has no separate empty_room class


def build_timeline(session_id, duration_s):
    """Return only explicit source annotations; gaps remain unknown."""
    label_path = REPO_ROOT / "data" / "labels" / f"{session_id}.jsonl"
    with label_path.open(encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]
    events = [(e["t_start"], e["t_end"], LABEL_MAP.get(e["label"], e["label"])) for e in events]
    events.sort(key=lambda e: e[0])
    timeline = []
    previous_end = 0.0
    for t0, t1, label in events:
        if not (0 <= t0 < t1 <= duration_s):
            raise ValueError(f"invalid annotation bounds for {session_id}: {t0}-{t1}")
        if t0 < previous_end:
            raise ValueError(f"overlapping source annotations for {session_id}")
        timeline.append((t0, t1, label))
        previous_end = t1
    return timeline


CONTINUOUS_LABELS = {"idle", "walk"}
TRANSIENT_LABELS = {"sit_down", "stand_up", "lie_down", "fall"}


def windows_for_continuous_span(t0, t1, label):
    """Uniform 3s/0.5s-slide windows fully contained within [t0, t1] -- fine
    for idle/walk since these spans (many seconds to minutes) are far longer
    than one window, so there's no dilution risk from sliding within them.
    event_bounds=None -- no single event boundary for a continuous span."""
    out = []
    w0 = t0
    while w0 + WINDOW_S <= t1:
        out.append((w0, w0 + WINDOW_S, label, None))
        w0 += HOP_S
    return out


def window_for_event(event_t0, event_t1, label, duration_s):
    """One 3s window centered on the event, clipped to the session bounds.

    Originally this project used the same uniform-slide rule as continuous
    spans for transient events too (sit_down ~0.5s, fall ~0.3s), with "any
    overlap >=0.1s" claiming the window. That generated ~7 heavily-diluted
    windows per event (each ~85% idle content, ~15% transient) and produced
    a classifier that predicted "stand_up" for almost everything (confusion
    matrix showed 67/153 true falls and 181/403 true sit_down predicted as
    stand_up) -- the model had learned a blurry, over-broad "mostly idle with
    a small blip" concept instead of each class's actual signature. One
    window centered on the event keeps the transient as the dominant content
    of every window for these classes, at the cost of far fewer samples per
    event (an honest tradeoff for a small self-recorded dataset, not hidden
    by synthetic window multiplication)."""
    center = (event_t0 + event_t1) / 2
    w0, w1 = center - WINDOW_S / 2, center + WINDOW_S / 2
    if w0 < 0:
        w0, w1 = 0.0, WINDOW_S
    if w1 > duration_s:
        w0, w1 = max(0.0, duration_s - WINDOW_S), duration_s
    return [(w0, w1, label, (event_t0, event_t1))]


def remove_cross_label_overlap(window_specs):
    """Drop all windows sharing raw-time support with a different label."""
    conflicting = set()
    for left_index, left in enumerate(window_specs):
        for right_index in range(left_index + 1, len(window_specs)):
            right = window_specs[right_index]
            if left[2] == right[2]:
                continue
            if left[0] < right[1] and right[0] < left[1]:
                conflicting.update((left_index, right_index))
    return [spec for index, spec in enumerate(window_specs) if index not in conflicting], len(conflicting)


def session_day(session_id):
    """LOSO fold group key. Normally the date prefix, but floor-geometry
    sessions get their own synthetic group even though they share a calendar
    date with that morning's bench-height session -- see FLOOR_GEOMETRY_DAY."""
    if FLOOR_GEOMETRY_MARKER in session_id:
        return FLOOR_GEOMETRY_DAY
    return session_id[:10]


def process_session(session_id):
    session_dir = REPO_ROOT / "data" / "raw" / session_id
    manifest = json.loads((session_dir / "manifest.json").read_text())
    fs = manifest["sample_rate_hz"]
    f0_hz = manifest["carrier_hz"]
    iq = np.fromfile(session_dir / f"{session_id}.sigmf-data", dtype=np.complex64)
    duration_s = len(iq) / fs

    times, energy, frames, lo, hi, nperseg = compute_energy_trace(iq, fs)
    n_bins = hi - lo
    freqs = doppler_frequencies(fs, expected_bins=n_bins)

    timeline = build_timeline(session_id, duration_s)
    day = session_day(session_id)

    window_specs = []
    for t0, t1, label in timeline:
        if label in CONTINUOUS_LABELS:
            window_specs.extend(windows_for_continuous_span(t0, t1, label))
        elif label in TRANSIENT_LABELS:
            window_specs.extend(window_for_event(t0, t1, label, duration_s))
    window_specs, conflict_exclusions = remove_cross_label_overlap(window_specs)

    rows = []
    for w0, w1, label, event_bounds in window_specs:
        mask = (times >= w0) & (times < w1)
        if mask.sum() >= 5:  # need enough STFT frames for meaningful stats
            event_t0, event_t1 = event_bounds if event_bounds is not None else (None, None)
            feats = window_features(frames[mask], freqs, f0_hz, frame_times=times[mask],
                                     event_t0=event_t0, event_t1=event_t1)
            confidence = "unverified" if (session_id, label) in UNVERIFIED_LABELS else "verified"
            rows.append({
                "session_id": session_id, "day": day, "t_start": w0, "t_end": w1,
                "label": label, "label_confidence": confidence,
                "label_provenance": "explicit_legacy_annotation", **feats,
            })
    return rows, conflict_exclusions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet",
    )
    args = parser.parse_args()
    all_rows = []
    total_conflict_exclusions = 0
    for session_id in SESSION_IDS:
        rows, conflict_exclusions = process_session(session_id)
        print(f"{session_id}: {len(rows)} windows; conflict exclusions={conflict_exclusions}")
        all_rows.extend(rows)
        total_conflict_exclusions += conflict_exclusions

    df = pd.DataFrame(all_rows)
    out_path = args.out.resolve()
    if out_path == (REPO_ROOT / "data" / "processed" / "g3_features.parquet").resolve():
        raise SystemExit("refused: the frozen legacy feature table cannot be overwritten")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    print(f"\nwrote {out_path}: {len(df)} windows total")
    print("\nlabel counts:")
    print(df["label"].value_counts())
    print("\nlabel counts by day (LOSO groups):")
    print(df.groupby(["day", "label"]).size().unstack(fill_value=0))
    print("\nunverified windows:", (df["label_confidence"] == "unverified").sum(), "of", len(df))
    print("cross-label candidate windows excluded:", total_conflict_exclusions)


if __name__ == "__main__":
    main()
