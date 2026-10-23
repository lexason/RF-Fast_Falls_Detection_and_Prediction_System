#!/usr/bin/env python3
"""G3 classifier v5: real LOSO (leave-one-day-out) evaluation of the
5-class stage2 design (adds "noise" to sit_down/stand_up/lie_down/fall),
on top of the 2026-08-02 event-segmentation fix -- see STATE.md.

This exists because the numbers reported earlier today (fall recall
0.170->0.574, specificity ->0.957) were IN-SAMPLE replay checks: the same
sessions the deployed model trained on. That's real evidence the
segmentation fix matters, but not a trustworthy generalization estimate,
and CLAUDE.md Prime Directive 7 forbids treating anything but LOSO/
leave-one-session-out numbers as real. This script retrains per held-out
day (exactly like models/train_hierarchical.py's original v3 evaluation,
extended to 5 stage2 classes) and, critically, pools OUT-OF-FOLD p_fall
probabilities across all folds to calibrate v5's fall_decision_threshold
honestly -- the same methodology as the original 2026-07-31 threshold fix,
never swept on in-sample data.

The 2026-08-02 noise-class day (33 examples from
2026-08-02_clean_scripted_session) becomes its own LOSO fold automatically,
grouped by day like every other session -- a real, if thin, held-out test
of whether "noise" generalizes at all, not just an in-sample sanity check.

Usage:
    python models/loso_v5.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xgboost as xgb
from sklearn.metrics import f1_score, confusion_matrix

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "features"))
from micro_doppler import FEATURE_NAMES  # noqa: E402

STAGE1_CLASSES = ["idle", "walk", "transient"]
TRANSIENT_CLASSES = ["sit_down", "stand_up", "lie_down", "fall", "noise"]


def softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def main():
    df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_features_v5_with_noise.parquet")
    out_dir = REPO_ROOT / "experiments" / "g3_classifier_v5"
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_classes = ["idle", "walk"] + TRANSIENT_CLASSES
    days = sorted(df["day"].unique())
    all_true, all_pred = [], []
    fold_results = []
    pooled_p_fall, pooled_is_fall = [], []  # out-of-fold, for honest threshold calibration

    for held_out in days:
        train_df = df[df["day"] != held_out]
        test_df = df[df["day"] == held_out]

        y1_train = train_df["label"].apply(lambda l: l if l in ("idle", "walk") else "transient")
        s1_idx = {c: i for i, c in enumerate(STAGE1_CLASSES)}
        y1_train_idx = np.array([s1_idx[y] for y in y1_train])
        X_train = train_df[FEATURE_NAMES].values
        counts1 = y1_train.value_counts()
        w1 = {c: len(y1_train) / (3 * n) for c, n in counts1.items()}
        sw1 = np.array([w1[y] for y in y1_train])
        clf1 = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                  objective="multi:softmax", num_class=3,
                                  eval_metric="mlogloss", random_state=0)
        clf1.fit(X_train, y1_train_idx, sample_weight=sw1)

        transient_train = train_df[train_df["label"].isin(TRANSIENT_CLASSES)]
        if transient_train.empty or transient_train["label"].nunique() < 2:
            print(f"[v5] fold held_out={held_out}: SKIPPED (insufficient transient diversity in training fold)")
            continue
        s2_idx = {c: i for i, c in enumerate(TRANSIENT_CLASSES)}
        X2_train = transient_train[FEATURE_NAMES].values
        y2_train_idx = np.array([s2_idx[y] for y in transient_train["label"]])
        counts2 = transient_train["label"].value_counts()
        w2 = {c: len(transient_train) / (len(TRANSIENT_CLASSES) * n) for c, n in counts2.items()}
        sw2 = np.array([w2[y] for y in transient_train["label"]])
        clf2 = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                  objective="multi:softmax", num_class=len(TRANSIENT_CLASSES),
                                  eval_metric="mlogloss", random_state=0)
        clf2.fit(X2_train, y2_train_idx, sample_weight=sw2)

        X_test = test_df[FEATURE_NAMES].values
        y_test = test_df["label"].values
        s1_pred_idx = clf1.predict(X_test)
        s1_pred = [STAGE1_CLASSES[i] for i in s1_pred_idx]

        final_pred = []
        transient_mask = [p == "transient" for p in s1_pred]
        if any(transient_mask):
            s2_pred_idx = clf2.predict(X_test[transient_mask])
            s2_iter = iter([TRANSIENT_CLASSES[i] for i in s2_pred_idx])
        else:
            s2_iter = iter([])
        for p in s1_pred:
            final_pred.append(p if p != "transient" else next(s2_iter))

        macro_f1 = f1_score(y_test, final_pred, labels=eval_classes, average="macro", zero_division=0)
        fold_results.append({"held_out_day": held_out, "n_train": len(train_df),
                              "n_test": len(test_df), "macro_f1": macro_f1})
        all_true.extend(y_test)
        all_pred.extend(final_pred)
        print(f"[v5] fold held_out={held_out}: n_train={len(train_df)} n_test={len(test_df)} macro_F1={macro_f1:.3f}")

        # Pooled out-of-fold p_fall -- ONLY on the properly-scoped population
        # (windows classify_transient() actually sees in deployment), computed
        # with THIS FOLD'S held-out models, never touching test_df's own labels.
        test_transient = test_df[test_df["label"].isin(TRANSIENT_CLASSES)]
        if len(test_transient):
            Xt = test_transient[FEATURE_NAMES].values
            p1_raw = clf1.predict_proba(Xt)
            p_transient = p1_raw[:, STAGE1_CLASSES.index("transient")]
            p2_raw = clf2.predict_proba(Xt)
            p_fall_given_t = p2_raw[:, TRANSIENT_CLASSES.index("fall")]
            p_fall = p_transient * p_fall_given_t
            pooled_p_fall.extend(p_fall.tolist())
            pooled_is_fall.extend((test_transient["label"] == "fall").tolist())

    overall_macro_f1 = f1_score(all_true, all_pred, labels=eval_classes, average="macro", zero_division=0)
    per_class_f1 = f1_score(all_true, all_pred, labels=eval_classes, average=None, zero_division=0)
    cm = confusion_matrix(all_true, all_pred, labels=eval_classes)

    pooled_p_fall = np.array(pooled_p_fall)
    pooled_is_fall = np.array(pooled_is_fall)
    print(f"\npooled out-of-fold transient population: {len(pooled_p_fall)} windows "
          f"({pooled_is_fall.sum()} fall)")

    sweep = []
    best = None
    for thresh in np.arange(0.05, 0.96, 0.05):
        pred_fall = pooled_p_fall >= thresh
        recall = (pred_fall & pooled_is_fall).sum() / pooled_is_fall.sum() if pooled_is_fall.sum() else float("nan")
        specificity = ((~pred_fall) & (~pooled_is_fall)).sum() / (~pooled_is_fall).sum() if (~pooled_is_fall).sum() else float("nan")
        sweep.append({"threshold": float(thresh), "recall": float(recall), "specificity": float(specificity)})
        print(f"  thresh={thresh:.2f}  recall={recall:.3f}  specificity={specificity:.3f}")
        if recall >= 0.90 and specificity >= 0.90:
            best = thresh

    # Chosen operating point: max-min balanced (matches 2026-07-31's methodology)
    # if nothing clears both 0.90 targets.
    balanced = min(sweep, key=lambda s: abs(s["recall"] - s["specificity"]))

    results = {
        "tag": "v5_loso_out_of_fold",
        "model": "hierarchical two-stage (XGBoost+XGBoost), stage2 5-class incl. noise, "
                 "on top of the 2026-08-02 event-segmentation fix",
        "n_windows_total": len(df), "classes": eval_classes,
        "fold_results": fold_results, "overall_macro_f1": overall_macro_f1,
        "per_class_f1": dict(zip(eval_classes, per_class_f1.tolist())),
        "confusion_matrix": cm.tolist(), "confusion_matrix_labels": eval_classes,
        "fall_threshold_sweep_out_of_fold": sweep,
        "fall_threshold_clears_both_090": best,
        "fall_threshold_balanced_operating_point": balanced,
        "ac_macro_f1_target": 0.85, "ac_macro_f1_pass": overall_macro_f1 >= 0.85,
        "note": "fall_threshold_sweep_out_of_fold is genuinely held-out (each fold's p_fall "
                "computed by that fold's own models, never seeing that fold's labels during "
                "training) -- NOT the in-sample sweep reported earlier today, which is not "
                "trustworthy for calibration.",
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(eval_classes)), eval_classes, rotation=45, ha="right")
    ax.set_yticks(range(len(eval_classes)), eval_classes)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title(f"G3 v5 classifier -- LOSO confusion matrix\nmacro-F1={overall_macro_f1:.3f}")
    for i in range(len(eval_classes)):
        for j in range(len(eval_classes)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    print(f"\nwrote {out_dir}/results.json")
    print(f"overall macro-F1={overall_macro_f1:.3f} (AC>=0.85: {'PASS' if overall_macro_f1>=0.85 else 'FAIL'})")
    print(f"fall_threshold that clears both 0.90 targets (out-of-fold): {best}")
    print(f"balanced operating point: {balanced}")


if __name__ == "__main__":
    main()
