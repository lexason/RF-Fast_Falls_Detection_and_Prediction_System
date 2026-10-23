#!/usr/bin/env python3
"""G3 classifier v1: XGBoost on per-window micro-Doppler features, leave-one-
session-out (LOSO) cross-validation across the 4 dataset days.

CLAUDE.md §6 G3 AC: "leave-one-session-out macro-F1 >= 0.85 across the 6
activity classes on self-recorded data (report full confusion matrix; falls
recall >= 0.90 at specificity >= 0.90)". Prime Directive 7 forbids random
train/test splits on windowed time-series (temporal-leak honesty rule) --
LOSO by day is the only validation used here, never a random split.

Runs two experiments, not one: PRIMARY uses all windows; SENSITIVITY excludes
the "unverified" windows the 2026-07-28 direction-verify QA pass could not
confirm clean (see STATE.md), to see whether they're propping up or dragging
down the headline number rather than silently trusting them either way.

Usage:
    python models/train_v1.py
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
from sklearn.metrics import f1_score, confusion_matrix, classification_report

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "features"))
from micro_doppler import FEATURE_NAMES  # noqa: E402 -- single source of truth, don't duplicate the list here

CLASSES = ["idle", "walk", "sit_down", "stand_up", "lie_down", "fall"]


def run_loso(df, out_dir, tag, classes):
    days = sorted(df["day"].unique())
    all_true, all_pred = [], []
    fold_results = []
    label_to_idx = {c: i for i, c in enumerate(classes)}

    for held_out in days:
        train_df = df[df["day"] != held_out]
        test_df = df[df["day"] == held_out]

        X_train = train_df[FEATURE_NAMES].values
        y_train = train_df["label"].values
        X_test = test_df[FEATURE_NAMES].values
        y_test = test_df["label"].values

        clf = xgb.XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            objective="multi:softmax", num_class=len(classes),
            eval_metric="mlogloss", random_state=0,
        )
        y_train_idx = np.array([label_to_idx[y] for y in y_train])

        # Class-balanced sample weights: idle/walk outnumber fall/lie_down ~40:1 in this
        # small self-recorded dataset, and the unweighted model was defaulting to the
        # majority classes for ambiguous windows. Inverse-frequency weighting is the
        # standard fix for this kind of imbalance, tried before concluding the AC gap
        # is a fundamental data-size limit rather than a remaining tunable issue.
        class_counts = pd.Series(y_train).value_counts()
        class_weight = {c: len(y_train) / (len(class_counts) * n) for c, n in class_counts.items()}
        sample_weight = np.array([class_weight[y] for y in y_train])

        clf.fit(X_train, y_train_idx, sample_weight=sample_weight)
        y_pred_idx = clf.predict(X_test)
        y_pred = [classes[i] for i in y_pred_idx]

        macro_f1 = f1_score(y_test, y_pred, labels=classes, average="macro", zero_division=0)
        fold_results.append({
            "held_out_day": held_out, "n_train": len(train_df), "n_test": len(test_df),
            "macro_f1": macro_f1,
        })
        all_true.extend(y_test)
        all_pred.extend(y_pred)
        print(f"[{tag}] fold held_out={held_out}: n_train={len(train_df)} n_test={len(test_df)} macro_F1={macro_f1:.3f}")

    overall_macro_f1 = f1_score(all_true, all_pred, labels=classes, average="macro", zero_division=0)
    per_class_f1 = f1_score(all_true, all_pred, labels=classes, average=None, zero_division=0)
    cm = confusion_matrix(all_true, all_pred, labels=classes)

    # Falls recall @ specificity, binarized fall-vs-rest over pooled LOSO predictions
    y_true_bin = np.array([1 if t == "fall" else 0 for t in all_true])
    y_pred_bin = np.array([1 if p == "fall" else 0 for p in all_pred])
    tp = int(((y_true_bin == 1) & (y_pred_bin == 1)).sum())
    fn = int(((y_true_bin == 1) & (y_pred_bin == 0)).sum())
    tn = int(((y_true_bin == 0) & (y_pred_bin == 0)).sum())
    fp = int(((y_true_bin == 0) & (y_pred_bin == 1)).sum())
    fall_recall = tp / (tp + fn) if (tp + fn) else float("nan")
    fall_specificity = tn / (tn + fp) if (tn + fp) else float("nan")

    report = classification_report(all_true, all_pred, labels=classes, zero_division=0, output_dict=True)

    results = {
        "tag": tag,
        "n_windows_total": len(df),
        "classes": classes,
        "fold_results": fold_results,
        "overall_macro_f1": overall_macro_f1,
        "per_class_f1": dict(zip(classes, per_class_f1.tolist())),
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": classes,
        "fall_recall": fall_recall,
        "fall_specificity": fall_specificity,
        "fall_confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        "classification_report": report,
        "ac_macro_f1_target": 0.85,
        "ac_macro_f1_pass": overall_macro_f1 >= 0.85,
        "ac_fall_recall_target": 0.90,
        "ac_fall_specificity_target": 0.90,
        "ac_fall_pass": fall_recall >= 0.90 and fall_specificity >= 0.90,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"results_{tag}.json").write_text(json.dumps(results, indent=2))

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title(f"G3 classifier v1 ({tag}) -- LOSO confusion matrix\nmacro-F1={overall_macro_f1:.3f}")
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(out_dir / f"confusion_matrix_{tag}.png", dpi=120)
    plt.close(fig)

    return results


def main():
    df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_features.parquet")
    out_dir = REPO_ROOT / "experiments" / "g3_classifier_v1"

    print("=== PRIMARY: all windows ===")
    primary = run_loso(df, out_dir, "primary_all_data", CLASSES)

    print("\n=== SENSITIVITY: unverified windows excluded ===")
    df_verified = df[df["label_confidence"] == "verified"]
    # lie_down has ZERO verified windows anywhere in the dataset (all 4 lie_down_reps
    # sessions were flagged unverified by the direction-verify QA pass, STATE.md
    # 2026-07-28/-29) -- drop it from this experiment's class list rather than crash
    # or silently pretend it's evaluable with zero ground truth.
    sensitivity_classes = [c for c in CLASSES if c != "lie_down"]
    print(f"excluded {len(df) - len(df_verified)} unverified windows ({len(df_verified)} remain); "
          f"lie_down dropped from this experiment's classes -- zero verified windows exist for it")
    sensitivity = run_loso(df_verified, out_dir, "sensitivity_verified_only", sensitivity_classes)

    print(f"\nPRIMARY macro-F1={primary['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if primary['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"PRIMARY fall recall={primary['fall_recall']:.3f} specificity={primary['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if primary['ac_fall_pass'] else 'FAIL'})")
    print(f"SENSITIVITY macro-F1={sensitivity['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if sensitivity['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"SENSITIVITY fall recall={sensitivity['fall_recall']:.3f} specificity={sensitivity['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if sensitivity['ac_fall_pass'] else 'FAIL'})")


if __name__ == "__main__":
    main()
