"""Deterministic Product-A fall-vs-hard-negative DEVELOPMENT baseline.

The model is deliberately small and interpretable.  It operates only after a
motion event has been detected and does not share Product-B activity labels or
thresholds.  No function in this module promotes or deploys a model.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, roc_auc_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

# Deliberately the pre-2026-09-12 raw-Hz names: this module only ever reads
# the frozen data/processed/g3_features_v2_conflict_free.parquet dataset,
# which was never rebuilt under the velocity-normalized feature schema (see
# features/micro_doppler.py's 2026-09-12 note). Do not rename to match the
# new *_mps/*_mps2 columns -- that dataset's columns are still raw Hz.
PHYSICS_FEATURE_NAMES = [
    "doppler_bandwidth_hz",
    "energy_db",
    "transient_score_db",
    "descent_speed_hz_per_s",
    "post_event_stillness_db",
    "event_duration_s",
]
TRANSIENT_LABELS = {"sit_down", "stand_up", "lie_down", "fall"}


def build_pipeline() -> Pipeline:
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=1.0,
            penalty="l2",
            class_weight="balanced",
            solver="liblinear",
            fit_intercept=True,
            random_state=0,
            max_iter=2000,
        ),
    )


def transient_frame(frame: pd.DataFrame, *, require_all_labels: bool = True) -> pd.DataFrame:
    selected = frame[frame["label"].isin(TRANSIENT_LABELS)].copy()
    if require_all_labels and set(selected["label"]) != TRANSIENT_LABELS:
        raise ValueError("development data must contain every transient activity label")
    if not {"fall"}.issubset(selected["label"]) or not (selected["label"] != "fall").any():
        raise ValueError("development data must contain falls and hard-negative transients")
    values = selected[PHYSICS_FEATURE_NAMES].to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("Product-A feature matrix contains NaN or infinity")
    return selected


def binary_target(frame: pd.DataFrame) -> np.ndarray:
    return (frame["label"] == "fall").to_numpy(dtype=np.int64)


def positive_scores(model: Pipeline, values: np.ndarray) -> np.ndarray:
    classifier = model.named_steps["logisticregression"]
    positive_index = list(classifier.classes_).index(1)
    return model.predict_proba(values)[:, positive_index]


def grouped_oof_scores(
    frame: pd.DataFrame,
    *,
    require_all_labels: bool = True,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, object]]]:
    selected = transient_frame(frame, require_all_labels=require_all_labels)
    truth = binary_target(selected)
    groups = selected["day"].astype(str).to_numpy()
    values = selected[PHYSICS_FEATURE_NAMES].to_numpy(dtype=np.float64)
    scores = np.empty(len(selected), dtype=np.float64)
    fold_results: list[dict[str, object]] = []
    for held_out in sorted(set(groups)):
        train_mask = groups != held_out
        test_mask = ~train_mask
        model = build_pipeline()
        model.fit(values[train_mask], truth[train_mask])
        fold_score = positive_scores(model, values[test_mask])
        scores[test_mask] = fold_score
        fold_truth = truth[test_mask]
        fold_results.append(
            {
                "held_out_day_or_geometry": held_out,
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
                "n_falls": int(fold_truth.sum()),
                "auroc": float(roc_auc_score(fold_truth, fold_score)),
                "auprc": float(average_precision_score(fold_truth, fold_score)),
            }
        )
    return truth, scores, fold_results


def threshold_metrics(truth: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, object]:
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(truth, predicted, labels=[0, 1]).ravel()
    recall = tp / (tp + fn) if tp + fn else math.nan
    specificity = tn / (tn + fp) if tn + fp else math.nan
    ppv = tp / (tp + fp) if tp + fp else None
    return {
        "threshold": float(threshold),
        "recall": float(recall),
        "specificity": float(specificity),
        "ppv": float(ppv) if ppv is not None else None,
        "tp": int(tp),
        "fn": int(fn),
        "fp": int(fp),
        "tn": int(tn),
    }


def diagnostic_balanced_point(truth: np.ndarray, scores: np.ndarray) -> dict[str, object]:
    rows = [threshold_metrics(truth, scores, threshold) for threshold in np.linspace(0.0, 1.0, 1001)]
    return max(rows, key=lambda row: (min(row["recall"], row["specificity"]), row["specificity"], -row["threshold"]))


def discrimination_metrics(truth: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    return {
        "auroc": float(roc_auc_score(truth, scores)),
        "auprc": float(average_precision_score(truth, scores)),
        "brier": float(brier_score_loss(truth, scores)),
    }


def export_pipeline(model: Pipeline) -> dict[str, object]:
    scaler: StandardScaler = model.named_steps["standardscaler"]
    classifier: LogisticRegression = model.named_steps["logisticregression"]
    return {
        "schema_version": "1.0",
        "model_type": "standard_scaler_plus_l2_logistic_regression",
        "feature_names": PHYSICS_FEATURE_NAMES,
        "mean": [float(value) for value in scaler.mean_],
        "scale": [float(value) for value in scaler.scale_],
        "coefficient": [float(value) for value in classifier.coef_[0]],
        "intercept": float(classifier.intercept_[0]),
        "classes": [int(value) for value in classifier.classes_],
        "score_semantics": "uncalibrated_development_score_not_probability",
        "fall_decision_threshold": None,
    }


def score_exported_model(artifact: Mapping[str, object], features: Mapping[str, float]) -> float:
    names = artifact.get("feature_names")
    if names != PHYSICS_FEATURE_NAMES:
        raise ValueError("Product-A feature contract mismatch")
    values = np.asarray([features[name] for name in names], dtype=np.float64)
    mean = np.asarray(artifact["mean"], dtype=np.float64)
    scale = np.asarray(artifact["scale"], dtype=np.float64)
    coefficient = np.asarray(artifact["coefficient"], dtype=np.float64)
    intercept = float(artifact["intercept"])
    if not all(array.shape == values.shape for array in (mean, scale, coefficient)):
        raise ValueError("Product-A artifact dimensions do not match")
    if not np.all(np.isfinite(np.concatenate((values, mean, scale, coefficient, [intercept])))) or np.any(scale <= 0):
        raise ValueError("Product-A artifact or features contain invalid values")
    logit = float(np.dot((values - mean) / scale, coefficient) + intercept)
    if logit >= 0:
        return float(1.0 / (1.0 + math.exp(-logit)))
    exp_logit = math.exp(logit)
    return float(exp_logit / (1.0 + exp_logit))
