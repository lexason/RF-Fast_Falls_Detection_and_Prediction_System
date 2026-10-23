#!/usr/bin/env python3
"""G3 production model v5 (STAGED, not yet deployed -- see STATE.md
2026-08-02): stage2 5-class (adds "noise") trained on top of the
event-segmentation fix, not instead of it.

Context: v4 (models/production_v4/) attempted the same "noise" class idea
but was rejected -- it regressed real fall recall on curated data (e.g.
floor_fall_reps_b: 4/26 -> 0/26 correctly labeled "fall"). Root-caused to a
pre-existing train/inference event-segmentation mismatch: label_tool.py's
offline event detector (used to build every training label) merges
hysteresis crossings within 0.6s into one complete event; the streaming
LiveEventDetector used at inference did not, fragmenting a single real
transition into several incomplete-looking pieces. Fixed in
inference/realtime_classifier.py (LiveEventDetector now does the same
bounded merge-gap). Validated (STATE.md): 15/20 curated sessions now match
the trusted offline event count EXACTLY; full replay scoring with the
EXISTING v3 model (no retraining) already lifted fall recall 0.170->0.574
and specificity 0.904->0.938 on 257 events across those matching sessions
(in-sample check, not LOSO -- flagged honestly, not a final number).

This script retrains stage2 with a "noise" class built from 33 confirmed-
noise events (2026-08-02_clean_scripted_session's pure-walking and
post-session-sitting windows, replayed through the FIXED detector -- 33
events, down from 77 with the old fragmenting detector, because merging
consolidated many footstep-level fragments into fewer, more complete noise
bursts).

Usage:
    python models/train_production_v5.py
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
    df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_features_v5_with_noise.parquet")
    out_dir = REPO_ROOT / "models" / "production_v5"
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
        "model": "v5 hierarchical STAGED (stage1 idle/walk/transient -> stage2 "
                 "sit_down/stand_up/lie_down/fall/noise), built on top of the "
                 "2026-08-02 LiveEventDetector merge-gap fix -- see STATE.md",
        "trained_on": "data/processed/g3_features_v5_with_noise.parquet "
                       "(v3's 3487 windows + 33 new 'noise' windows from "
                       "2026-08-02_clean_scripted_session, extracted with the FIXED "
                       "streaming detector, not the fragmenting one v4 used)",
        "n_windows_total": len(df),
        "n_noise_windows": int((df["label"] == "noise").sum()),
        "feature_names": FEATURE_NAMES,
        "stage1_classes": STAGE1_CLASSES,
        "stage2_classes": TRANSIENT_CLASSES,
        "final_classes": ["idle", "walk"] + TRANSIENT_CLASSES,
        "fall_decision_threshold": None,
        "fall_threshold_calibration": "NOT YET RECALIBRATED -- must re-sweep against the "
                                       "5-class stage2 softmax (noise now competes for "
                                       "probability mass) before deployment. See STATE.md.",
        "fall_probability_formula": "p_fall = p(stage1=transient) * p(stage2=fall | transient)",
        "window_s": 3.0, "hop_s": 0.5,
        "requires": "inference/realtime_classifier.py's LiveEventDetector merge-gap fix "
                    "(2026-08-02) -- this model's event boundaries assume merged events, "
                    "same as v3 always did. Do NOT pair with a pre-fix LiveEventDetector.",
        "known_limitation": "noise class trained on 33 examples from a SINGLE session -- "
                             "no leave-one-session-out validation possible for this class "
                             "yet. Also unvalidated: full LOSO retrain-per-fold using the "
                             "fixed segmentation (current validation is in-sample replay "
                             "scoring against curated sessions, not held-out). Both should "
                             "happen before treating this as production-hardened.",
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
