#!/usr/bin/env python3
"""Grouped DEVELOPMENT evaluation for the hierarchical candidate recipe.

This evaluator never edits a model bundle or selects a deployable threshold.
It emits an evidence artifact and always keeps promotion blocked when the
required participant/room/site independence is absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "features"))
from micro_doppler import FEATURE_NAMES  # noqa: E402

STAGE1_CLASSES = ["idle", "walk", "transient"]
TRANSIENT_CLASSES = ["sit_down", "stand_up", "lie_down", "fall"]
FINAL_CLASSES = ["idle", "walk", *TRANSIENT_CLASSES]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fit_classifier(frame: pd.DataFrame, labels: pd.Series, classes: list[str]) -> xgb.XGBClassifier:
    indices = {name: index for index, name in enumerate(classes)}
    encoded = np.asarray([indices[value] for value in labels])
    counts = labels.value_counts()
    sample_weights = np.asarray([len(labels) / (len(classes) * counts[value]) for value in labels])
    classifier = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        objective="multi:softprob",
        num_class=len(classes),
        eval_metric="mlogloss",
        random_state=0,
        n_jobs=1,
    )
    classifier.fit(frame[FEATURE_NAMES].values, encoded, sample_weight=sample_weights)
    return classifier


def expected_calibration_error(target: np.ndarray, score: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = 0.0
    for index in range(bins):
        mask = (score >= edges[index]) & (score < edges[index + 1] if index < bins - 1 else score <= 1.0)
        if mask.any():
            result += mask.mean() * abs(float(target[mask].mean()) - float(score[mask].mean()))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet",
    )
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    candidate_dir = (args.candidate_dir or REPO_ROOT / "models" / "candidates" / args.candidate_id).resolve()
    try:
        candidate_metadata = json.loads((candidate_dir / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"candidate metadata cannot be read: {exc}") from exc
    if candidate_metadata.get("model_id") != args.candidate_id:
        raise SystemExit("candidate model_id does not match --candidate-id")
    if candidate_metadata.get("promotion_eligible") is not False:
        raise SystemExit("candidate must remain promotion-blocked during development evaluation")
    candidate_artifacts = candidate_metadata.get("artifact_sha256", {})
    required_artifacts = {"stage1_idle_walk_transient.onnx", "stage2_transient_subclass.onnx"}
    if not isinstance(candidate_artifacts, dict) or not required_artifacts.issubset(candidate_artifacts):
        raise SystemExit("candidate metadata does not bind both required ONNX artifacts")
    for filename, expected in candidate_artifacts.items():
        observed = sha256_file(candidate_dir / filename)
        if observed != expected:
            raise SystemExit(f"candidate artifact hash mismatch: {filename}")
    if candidate_metadata.get("dataset", {}).get("sha256") != sha256_file(dataset):
        raise SystemExit("evaluation dataset hash does not match candidate training metadata")
    frame = pd.read_parquet(dataset)
    if not np.all(np.isfinite(frame[FEATURE_NAMES].to_numpy(dtype=np.float64))):
        raise SystemExit("evaluation dataset contains non-finite features")

    oof_true: list[str] = []
    oof_predicted: list[str] = []
    oof_fall_score: list[float] = []
    fold_results = []
    for held_out in sorted(frame["day"].unique()):
        train = frame[frame["day"] != held_out]
        test = frame[frame["day"] == held_out]
        stage1_labels = train["label"].map(lambda value: value if value in {"idle", "walk"} else "transient")
        stage1 = fit_classifier(train, stage1_labels, STAGE1_CLASSES)
        transient_train = train[train["label"].isin(TRANSIENT_CLASSES)]
        if set(transient_train["label"]) != set(TRANSIENT_CLASSES):
            raise SystemExit(f"fold {held_out} lacks a transient training class")
        stage2 = fit_classifier(transient_train, transient_train["label"], TRANSIENT_CLASSES)

        stage1_probability = stage1.predict_proba(test[FEATURE_NAMES].values)
        stage2_probability = stage2.predict_proba(test[FEATURE_NAMES].values)
        stage1_prediction = np.argmax(stage1_probability, axis=1)
        stage2_prediction = np.argmax(stage2_probability, axis=1)
        predictions = [
            STAGE1_CLASSES[first] if STAGE1_CLASSES[first] != "transient" else TRANSIENT_CLASSES[second]
            for first, second in zip(stage1_prediction, stage2_prediction)
        ]
        fall_scores = (
            stage1_probability[:, STAGE1_CLASSES.index("transient")]
            * stage2_probability[:, TRANSIENT_CLASSES.index("fall")]
        )
        fold_macro = f1_score(test["label"], predictions, labels=FINAL_CLASSES, average="macro", zero_division=0)
        fold_results.append(
            {"held_out_day_or_geometry": str(held_out), "n_train": len(train), "n_test": len(test), "macro_f1": fold_macro}
        )
        oof_true.extend(map(str, test["label"]))
        oof_predicted.extend(predictions)
        oof_fall_score.extend(map(float, fall_scores))

    truth = np.asarray(oof_true)
    prediction = np.asarray(oof_predicted)
    score = np.asarray(oof_fall_score)
    macro_f1 = f1_score(truth, prediction, labels=FINAL_CLASSES, average="macro", zero_division=0)
    per_class = f1_score(truth, prediction, labels=FINAL_CLASSES, average=None, zero_division=0)
    matrix = confusion_matrix(truth, prediction, labels=FINAL_CLASSES)

    transient_mask = np.isin(truth, TRANSIENT_CLASSES)
    transient_target = (truth[transient_mask] == "fall").astype(int)
    transient_score = score[transient_mask]
    sweep = []
    for threshold in np.linspace(0.0, 1.0, 101):
        predicted_fall = transient_score >= threshold
        tp = int(np.sum(predicted_fall & (transient_target == 1)))
        fn = int(np.sum(~predicted_fall & (transient_target == 1)))
        fp = int(np.sum(predicted_fall & (transient_target == 0)))
        tn = int(np.sum(~predicted_fall & (transient_target == 0)))
        recall = tp / (tp + fn) if tp + fn else math.nan
        specificity = tn / (tn + fp) if tn + fp else math.nan
        ppv = tp / (tp + fp) if tp + fp else None
        sweep.append(
            {
                "threshold": round(float(threshold), 2),
                "recall": recall,
                "specificity": specificity,
                "ppv": ppv,
                "tp": tp,
                "fn": fn,
                "fp": fp,
                "tn": tn,
            }
        )
    both_target = [row for row in sweep if row["recall"] >= 0.9 and row["specificity"] >= 0.9]
    balanced = max(sweep, key=lambda row: min(row["recall"], row["specificity"]))
    report = {
        "schema_version": "1.0",
        "evaluation_id": f"{args.candidate_id}-grouped-development",
        "candidate_id": args.candidate_id,
        "candidate_bundle": {
            "path": str(candidate_dir.relative_to(REPO_ROOT)) if candidate_dir.is_relative_to(REPO_ROOT) else str(candidate_dir),
            "metadata_sha256": sha256_file(candidate_dir / "metadata.json"),
            "artifact_sha256": candidate_artifacts,
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluator": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
            "xgboost_version": xgb.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
        },
        "status": "FAILED_ACCEPTANCE_CRITERIA",
        "promotion_eligible": False,
        "split": "leave-one-day-or-geometry-out; not participant/site/room independent",
        "dataset": str(dataset),
        "n_windows": len(frame),
        "n_falls": int(np.sum(truth == "fall")),
        "fold_results": fold_results,
        "activity": {
            "macro_f1": macro_f1,
            "per_class_f1": dict(zip(FINAL_CLASSES, map(float, per_class))),
            "confusion_matrix": matrix.tolist(),
            "labels": FINAL_CLASSES,
            "target_macro_f1": 0.85,
            "gate_passed": bool(macro_f1 >= 0.85),
        },
        "fall_transient_subset": {
            "n": int(transient_mask.sum()),
            "n_falls": int(transient_target.sum()),
            "auroc": roc_auc_score(transient_target, transient_score),
            "auprc": average_precision_score(transient_target, transient_score),
            "brier": brier_score_loss(transient_target, transient_score),
            "ece_10_bins": expected_calibration_error(transient_target, transient_score),
            "threshold_090_recall_and_specificity_exists": bool(both_target),
            "balanced_development_point": balanced,
            "threshold_sweep": sweep,
        },
        "threshold_policy": None,
        "performance_gate_passed": False,
        "failure_reasons": [
            "no participant, room, site, or final-test independence",
            "single apparent researcher and one laboratory",
            "only 30 retained legacy fall windows",
            "threshold sweep is diagnostic and cannot calibrate deployment",
        ],
    }
    output = args.out or REPO_ROOT / "artifacts" / "evaluations" / f"{args.candidate_id}-grouped-development.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"refused: evaluation artifact already exists: {output}")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": report["status"],
                "macro_f1": macro_f1,
                "fall_auroc": report["fall_transient_subset"]["auroc"],
                "balanced_point": balanced,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
