#!/usr/bin/env python3
"""G3 production model v4 (STAGED, not yet deployed -- see STATE.md
2026-08-02 live-testing investigation): adds a 5th stage-2 class, "noise",
trained on 77 confirmed-noise events extracted from
data/processed/g3_features_v4_with_noise.parquet.

Root cause this addresses: stage2 (v3) was trained only on isolated
single-rep windows with genuine rest before/after. Live/naturalistic
streaming triggers the same hysteresis event detector on footstep- and
settling-energy bursts that are NOT real posture transitions, and v3 had no
"this isn't a real transition" option -- it was forced to pick among
sit_down/stand_up/lie_down/fall and collapsed mostly onto stand_up, with
fall as an unstable secondary mode (see STATE.md for the full event-level
breakdown: 227 events in a 20-minute scripted session against ~70-90 real
transitions, 82% argmax'd stand_up, and 11/11 fall-labeled events in that
replay landed on non-fall scripted phases).

The 77 noise examples come from two windows of
2026-08-02_clean_scripted_session with ZERO scripted transitions (pure
walking, and sitting quietly after the last rep) -- so their "noise" label
is ground truth by construction, not a judgment call on an ambiguous event.

Writes to models/production_v4/ (NOT models/production/) so the live
service, which loads from models/production/, is completely unaffected
until a human explicitly promotes this directory.

Usage:
    python models/train_production_v4.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from onnxmltools import convert_xgboost
from onnxmltools.convert.common.data_types import FloatTensorType

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "features"))
from micro_doppler import FEATURE_NAMES  # noqa: E402

TRANSIENT_CLASSES = ["sit_down", "stand_up", "lie_down", "fall", "noise"]
STAGE1_CLASSES = ["idle", "walk", "transient"]


def main():
    df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_features_v4_with_noise.parquet")
    out_dir = REPO_ROOT / "models" / "production_v4"
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df[FEATURE_NAMES].values
    y1 = df["label"].apply(lambda l: l if l in ("idle", "walk") else "transient")
    s1_idx = {c: i for i, c in enumerate(STAGE1_CLASSES)}
    y1_idx = np.array([s1_idx[y] for y in y1])
    counts1 = y1.value_counts()
    w1 = {c: len(y1) / (3 * n) for c, n in counts1.items()}
    sw1 = np.array([w1[y] for y in y1])

    clf1 = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                              objective="multi:softmax", num_class=3,
                              eval_metric="mlogloss", random_state=0)
    clf1.fit(X, y1_idx, sample_weight=sw1)

    transient_df = df[df["label"].isin(TRANSIENT_CLASSES)]
    X2 = transient_df[FEATURE_NAMES].values
    s2_idx = {c: i for i, c in enumerate(TRANSIENT_CLASSES)}
    y2_idx = np.array([s2_idx[y] for y in transient_df["label"]])
    counts2 = transient_df["label"].value_counts()
    w2 = {c: len(transient_df) / (5 * n) for c, n in counts2.items()}
    sw2 = np.array([w2[y] for y in transient_df["label"]])

    clf2 = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                              objective="multi:softmax", num_class=5,
                              eval_metric="mlogloss", random_state=0)
    clf2.fit(X2, y2_idx, sample_weight=sw2)

    n_features = len(FEATURE_NAMES)
    initial_type = [("input", FloatTensorType([None, n_features]))]
    onnx1 = convert_xgboost(clf1, initial_types=initial_type)
    onnx2 = convert_xgboost(clf2, initial_types=initial_type)
    (out_dir / "stage1_idle_walk_transient.onnx").write_bytes(onnx1.SerializeToString())
    (out_dir / "stage2_transient_subclass.onnx").write_bytes(onnx2.SerializeToString())

    metadata = {
        "model": "v4 hierarchical STAGED (stage1 idle/walk/transient -> stage2 "
                 "sit_down/stand_up/lie_down/fall/noise) -- not yet deployed, "
                 "see STATE.md 2026-08-02",
        "trained_on": "data/processed/g3_features_v4_with_noise.parquet "
                       "(v3's 3487 windows + 77 new 'noise' windows from "
                       "2026-08-02_clean_scripted_session's confirmed zero-transition segments)",
        "n_windows_total": len(df),
        "n_noise_windows": int((df["label"] == "noise").sum()),
        "feature_names": FEATURE_NAMES,
        "stage1_classes": STAGE1_CLASSES,
        "stage2_classes": TRANSIENT_CLASSES,
        "final_classes": ["idle", "walk"] + TRANSIENT_CLASSES,
        "fall_decision_threshold": None,
        "fall_threshold_calibration": "NOT YET RECALIBRATED -- v3's threshold=0.50 was calibrated "
                                       "against a 4-class stage2 softmax; with 'noise' now competing "
                                       "for probability mass the same threshold has different meaning. "
                                       "Must re-sweep before deployment (see STATE.md).",
        "fall_probability_formula": "p_fall = p(stage1=transient) * p(stage2=fall | transient)",
        "window_s": 3.0, "hop_s": 0.5,
        "known_limitation": "noise class trained on 77 examples from a SINGLE session "
                             "(2026-08-02_clean_scripted_session) -- no leave-one-session-out "
                             "validation possible for this class yet. Treat as a first pass; "
                             "more noise-class data from the 2026-08-05 (Tuesday) live session "
                             "should be folded in before treating this as production-hardened.",
        "calibration_note": "This threshold governs ONLY the binary fall-vs-not-fall decision, calibrated "
                             "separately from stage1/stage2's own argmax outputs (which remain uncalibrated -- "
                             "used as-is for idle/walk/sit_down/stand_up/lie_down/noise predictions).",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print(f"wrote {out_dir}/stage1_idle_walk_transient.onnx")
    print(f"wrote {out_dir}/stage2_transient_subclass.onnx")
    print(f"wrote {out_dir}/metadata.json")
    print(f"trained on {len(df)} windows ({len(transient_df)} transient, "
          f"{int((df['label']=='noise').sum())} noise)")


if __name__ == "__main__":
    main()
