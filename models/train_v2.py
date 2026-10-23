#!/usr/bin/env python3
"""G3 classifier v2: train the compact CNN (cnn_v2.FMCWGaitNetCW) on
spectrogram patches, leave-one-session-out (LOSO) by day -- same validation
discipline, same metrics, same two-experiment structure (primary + unverified-
excluded sensitivity check) as models/train_v1.py, for a direct, fair
comparison against the XGBoost baseline.

CLAUDE.md §6 G3 AC: LOSO macro-F1 >= 0.85, falls recall >= 0.90 @
specificity >= 0.90. Prime Directive 7: LOSO only, never a random split.

Usage:
    python models/train_v2.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import f1_score, confusion_matrix, classification_report

from cnn_v2 import FMCWGaitNetCW

REPO_ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["idle", "walk", "sit_down", "stand_up", "lie_down", "fall"]
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MAX_EPOCHS = 60
PATIENCE = 10
BATCH_SIZE = 32
VAL_FRAC = 0.15
SEED = 0


def make_loader(X, y, batch_size, shuffle):
    ds = TensorDataset(torch.from_numpy(X).unsqueeze(1), torch.from_numpy(y).long())
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)


def train_one_fold(X_train, y_train, X_val, y_val, n_classes, class_weight):
    model = FMCWGaitNetCW(n_classes).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    weight_t = torch.tensor(class_weight, dtype=torch.float32, device=DEVICE)
    criterion = nn.CrossEntropyLoss(weight=weight_t)

    train_loader = make_loader(X_train, y_train, BATCH_SIZE, shuffle=True)
    val_loader = make_loader(X_val, y_val, BATCH_SIZE, shuffle=False)

    best_val_f1, best_state, epochs_no_improve = -1.0, None, 0
    for epoch in range(MAX_EPOCHS):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            opt.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            opt.step()

        model.eval()
        val_preds, val_true = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                pred = model(xb.to(DEVICE)).argmax(1).cpu().numpy()
                val_preds.extend(pred)
                val_true.extend(yb.numpy())
        val_f1 = f1_score(val_true, val_preds, average="macro", zero_division=0)

        if val_f1 > best_val_f1:
            best_val_f1, best_state, epochs_no_improve = val_f1, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= PATIENCE:
                break

    model.load_state_dict(best_state)
    return model, best_val_f1


def run_loso(X, meta_df, out_dir, tag, classes):
    days = sorted(meta_df["day"].unique())
    label_to_idx = {c: i for i, c in enumerate(classes)}
    all_true, all_pred = [], []
    fold_results = []
    rng = np.random.RandomState(SEED)

    for held_out in days:
        train_mask = (meta_df["day"] != held_out).values
        test_mask = (meta_df["day"] == held_out).values

        X_train_full, y_train_full = X[train_mask], meta_df["label"].values[train_mask]
        X_test, y_test = X[test_mask], meta_df["label"].values[test_mask]

        # carve a validation split out of TRAIN days only (never the held-out test day)
        idx = np.arange(len(X_train_full))
        rng.shuffle(idx)
        n_val = max(1, int(len(idx) * VAL_FRAC))
        val_idx, tr_idx = idx[:n_val], idx[n_val:]

        mu, sigma = X_train_full[tr_idx].mean(), X_train_full[tr_idx].std() + 1e-6
        X_tr = ((X_train_full[tr_idx] - mu) / sigma).astype(np.float32)
        X_va = ((X_train_full[val_idx] - mu) / sigma).astype(np.float32)
        X_te = ((X_test - mu) / sigma).astype(np.float32)

        y_tr = np.array([label_to_idx[y] for y in y_train_full[tr_idx]])
        y_va = np.array([label_to_idx[y] for y in y_train_full[val_idx]])

        counts = pd.Series(y_tr).value_counts()
        class_weight = np.array([len(y_tr) / (len(classes) * counts.get(i, 1)) for i in range(len(classes))])

        model, best_val_f1 = train_one_fold(X_tr, y_tr, X_va, y_va, len(classes), class_weight)

        model.eval()
        test_loader = make_loader(X_te, np.zeros(len(X_te), dtype=np.int64), BATCH_SIZE, shuffle=False)
        preds = []
        with torch.no_grad():
            for xb, _ in test_loader:
                preds.extend(model(xb.to(DEVICE)).argmax(1).cpu().numpy())
        y_pred = [classes[i] for i in preds]

        macro_f1 = f1_score(y_test, y_pred, labels=classes, average="macro", zero_division=0)
        fold_results.append({
            "held_out_day": held_out, "n_train": len(tr_idx), "n_val": len(val_idx), "n_test": len(X_test),
            "best_val_macro_f1": best_val_f1, "macro_f1": macro_f1,
        })
        all_true.extend(y_test)
        all_pred.extend(y_pred)
        print(f"[{tag}] fold held_out={held_out}: n_train={len(tr_idx)} n_val={len(val_idx)} "
              f"n_test={len(X_test)} val_F1={best_val_f1:.3f} test_macro_F1={macro_f1:.3f}")

    overall_macro_f1 = f1_score(all_true, all_pred, labels=classes, average="macro", zero_division=0)
    per_class_f1 = f1_score(all_true, all_pred, labels=classes, average=None, zero_division=0)
    cm = confusion_matrix(all_true, all_pred, labels=classes)

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
        "tag": tag, "model": "FMCWGaitNetCW (classifier v2)",
        "n_windows_total": len(meta_df), "classes": classes,
        "fold_results": fold_results, "overall_macro_f1": overall_macro_f1,
        "per_class_f1": dict(zip(classes, per_class_f1.tolist())),
        "confusion_matrix": cm.tolist(), "confusion_matrix_labels": classes,
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
    ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title(f"G3 classifier v2 ({tag}) -- LOSO confusion matrix\nmacro-F1={overall_macro_f1:.3f}")
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
    print(f"device: {DEVICE}")
    X = np.load(REPO_ROOT / "data" / "processed" / "g3_spectrogram_patches.npy")
    meta_df = pd.read_parquet(REPO_ROOT / "data" / "processed" / "g3_spectrogram_meta.parquet")
    out_dir = REPO_ROOT / "experiments" / "g3_classifier_v2"

    print("=== PRIMARY: all windows ===")
    primary = run_loso(X, meta_df, out_dir, "primary_all_data", CLASSES)

    print("\n=== SENSITIVITY: unverified windows excluded ===")
    verified_mask = (meta_df["label_confidence"] == "verified").values
    sensitivity_classes = [c for c in CLASSES if c != "lie_down"]
    print(f"excluded {(~verified_mask).sum()} unverified windows; lie_down dropped (zero verified windows)")
    sensitivity = run_loso(X[verified_mask], meta_df[verified_mask].reset_index(drop=True),
                            out_dir, "sensitivity_verified_only", sensitivity_classes)

    print(f"\nPRIMARY macro-F1={primary['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if primary['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"PRIMARY fall recall={primary['fall_recall']:.3f} specificity={primary['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if primary['ac_fall_pass'] else 'FAIL'})")
    print(f"SENSITIVITY macro-F1={sensitivity['overall_macro_f1']:.3f} (AC>=0.85: {'PASS' if sensitivity['ac_macro_f1_pass'] else 'FAIL'})")
    print(f"SENSITIVITY fall recall={sensitivity['fall_recall']:.3f} specificity={sensitivity['fall_specificity']:.3f} "
          f"(AC>=0.90/0.90: {'PASS' if sensitivity['ac_fall_pass'] else 'FAIL'})")


if __name__ == "__main__":
    main()
