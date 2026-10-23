#!/usr/bin/env python3
"""G3 classifier v3: hierarchical two-stage classifier.

Motivated by diagnostics run 2026-07-31 against v1/v2: idle/walk are already
well-separated (F1 0.85-0.93) from a flat 6-way XGBoost/CNN, while the real
difficulty is entirely concentrated in telling sit_down/stand_up/lie_down/fall
apart from EACH OTHER -- a much smaller, more separable sub-problem that a
flat 6-way classifier dilutes by training jointly against ~3100 idle/walk
windows outnumbering the ~250 transient windows roughly 12:1.

Stage 1 (3-way): idle vs walk vs "transient" (sit_down/stand_up/lie_down/fall
merged into one bucket). Expected to be near-trivial given v1/v2's existing
idle/walk performance.
Stage 2 (4-way): sit_down vs stand_up vs lie_down vs fall, trained ONLY on
true transient-labeled windows -- no longer drowned out by the majority
classes. This is the stage actually responsible for fall detection quality.

Evaluated end-to-end (stage 1's errors propagate into stage 2, exactly as a
real deployment would run) via the same LOSO-by-day, same metrics schema as
train_v1.py/train_v2.py for direct comparability.

Usage:
    python models/train_hierarchical.py
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
from micro_doppler import FEATURE_NAMES  # noqa: E402

CLASSES = ["idle", "walk", "sit_down", "stand_up", "lie_down", "fall"]
TRANSIENT_CLASSES = ["sit_down", "stand_up", "lie_down", "fall"]
STAGE1_CLASSES = ["idle", "walk", "transient"]


def run_loso(df, out_dir, tag, transient_classes=None):
    transient_classes = transient_classes or TRANSIENT_CLASSES
    eval_classes = ["idle", "walk"] + transient_classes
    days = sorted(df["day"].unique())
    all_true, all_pred = [], []
    fold_results = []

    for held_out in days:
        train_df = df[df["day"] != held_out]
        test_df = df[df["day"] == held_out]

        # --- Stage 1: idle / walk / transient ---
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

        # --- Stage 2: transient sub-classes only (may exclude lie_down for the
        # verified-only sensitivity run, which has zero verified lie_down windows) ---
        transient_train = train_df[train_df["label"].isin(transient_classes)]
        s2_idx = {c: i for i, c in enumerate(transient_classes)}
        X2_train = transient_train[FEATURE_NAMES].values
        y2_train_idx = np.array([s2_idx[y] for y in transient_train["label"]])
        counts2 = transient_train["label"].value_counts()
        w2 = {c: len(transient_train) / (len(transient_classes) * n) for c, n in counts2.items()}
        sw2 = np.array([w2[y] for y in transient_train["label"]])

        clf2 = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                  objective="multi:softmax", num_class=len(transient_classes),
                                  eval_metric="mlogloss", random_state=0)
        clf2.fit(X2_train, y2_train_idx, sample_weight=sw2)

        # --- End-to-end inference on the held-out day ---
        X_test = test_df[FEATURE_NAMES].values
        y_test = test_df["label"].values
        s1_pred_idx = clf1.predict(X_test)
        s1_pred = [STAGE1_CLASSES[i] for i in s1_pred_idx]

        final_pred = []
        transient_mask = [p == "transient" for p in s1_pred]
        if any(transient_mask):
            s2_pred_idx = clf2.predict(X_test[transient_mask])
            s2_iter = iter([transient_classes[i] for i in s2_pred_idx])
        else:
            s2_iter = iter([])
        for p in s1_pred:
            final_pred.append(p if p != "transient" else next(s2_iter))

        macro_f1 = f1_score(y_test, final_pred, labels=eval_classes, average="macro", zero_division=0)
        fold_results.append({"held_out_day": held_out, "n_train": len(train_df), "n_test": len(test_df), "macro_f1": macro_f1})
        all_true.extend(y_test)
        all_pred.extend(final_pred)
        print(f"[{tag}] fold held_out={held_out}: n_train={len(train_df)} n_test={len(test_df)} macro_F1={macro_f1:.3f}")

    overall_macro_f1 = f1_score(all_true, all_pred, labels=eval_classes, average="macro", zero_division=0)
    per_class_f1 = f1_score(all_true, all_pred, labels=eval_classes, average=None, zero_division=0)
    cm = confusion_matrix(all_true, all_pred, labels=eval_classes)

    y_true_bin = np.array([1 if t == "fall" else 0 for t in all_true])
    y_pred_bin = np.array([1 if p == "fall" else 0 for p in all_pred])
    tp = int(((y_true_bin == 1) & (y_pred_bin == 1)).sum())
    fn = int(((y_true_bin == 1) & (y_pred_bin == 0)).sum())
    tn = int(((y_true_bin == 0) & (y_pred_bin == 0)).sum())
    fp = int(((y_true_bin == 0) & (y_pred_bin == 1)).sum())
    fall_recall = tp / (tp + fn) if (tp + fn) else float("nan")
    fall_specificity = tn / (tn + fp) if (tn + fp) else float("nan")

    report = classification_report(all_true, all_pred, labels=eval_classes, zero_division=0, output_dict=True)
    results = {
        "tag": tag, "model": "hierarchical two-stage (XGBoost + XGBoost)",
        "n_windows_total": len(df), "classes": eval_classes,
        "fold_results": fold_results, "overall_macro_f1": overall_macro_f1,
        "per_class_f1": dict(zip(eval_classes, per_class_f1.tolist())),
        "confusion_matrix": cm.tolist(), "confusion_matrix_labels": eval_classes,
        "fall_recall": fall_recall, "fall_specificity": fall_specificity,
        "fall_confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        "classification_report": report,
        "ac_macro_f1_target": 0.85, "ac_macro_f1_pass": overall_macro_f1 >= 0.85,
        "ac_fall_recall_target": 0.90, "ac_fall_specificity_target": 0.90,
        "ac_fall_pass": fall_recall >= 0.90 and fall_specificity >= 0.90,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"results_{tag}.json").write_text(json.dumps(results, indent=2))

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(eval_classes)), eval_classes, rotation=45, ha="right")
    ax.set_yticks(range(len(eval_classes)), eval_classes)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title(f"G3 hierarchical classifier ({tag}) -- LOSO confusion matrix\nmacro-F1={overall_macro_f1:.3f}")
    for i in range(len(eval_classes)):
        for j in range(len(eval_classes)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(out_dir / f"confusion_matrix_{tag}.png", dpi=120)
    plt.close(fig)

    return results


def main():
    df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_features.parquet")
    out_dir = REPO_ROOT / "experiments" / "g3_classifier_hierarchical"

    print("=== PRIMARY: all windows ===")
    primary = run_loso(df, out_dir, "primary_all_data")

    print("\n=== SENSITIVITY: unverified windows excluded ===")
    df_verified = df[df["label_confidence"] == "verified"]
    print(f"excluded {len(df) - len(df_verified)} unverified windows ({len(df_verified)} remain)")
    sensitivity_transients = [c for c in TRANSIENT_CLASSES if c != "lie_down"]
    sensitivity = run_loso(df_verified, out_dir, "sensitivity_verified_only", sensitivity_transients)

    print(f"\nPRIMARY macro-F1={primary['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if primary['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"PRIMARY fall recall={primary['fall_recall']:.3f} specificity={primary['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if primary['ac_fall_pass'] else 'FAIL'})")
    print(f"SENSITIVITY macro-F1={sensitivity['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if sensitivity['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"SENSITIVITY fall recall={sensitivity['fall_recall']:.3f} specificity={sensitivity['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if sensitivity['ac_fall_pass'] else 'FAIL'})")


if __name__ == "__main__":
    main()
